-- Execute inteiro no SQL Editor do projeto indicado em supabase/config.json.
-- Cria somente objetos controlai_*. Não remove tabelas existentes.
begin;
create table if not exists public.controlai_members (
  email text primary key check(email = lower(email)),
  name text not null,
  role text not null check(role in ('admin','operador')),
  active boolean not null default true,
  user_id uuid unique references auth.users(id) on delete set null
);
create table if not exists public.controlai_state (
  id integer primary key check(id=1), revision bigint not null default 0,
  payload jsonb not null
);
create table if not exists public.controlai_audit (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(), user_id uuid not null,
  actor text not null, action text not null, details jsonb not null default '{}'
);
insert into public.controlai_members(email,name,role)
values ('arthurlopescorporativo@gmail.com','Arthur','admin') on conflict(email) do nothing;
insert into public.controlai_state(id,payload) values
(1,'{"estoque":[],"dataEst":"","obras":[],"itens":[],"nid":1,"pedidos":[],"entregas":[]}') on conflict(id) do nothing;

-- Sem acesso direto: todas as operações passam por funções autenticadas.
alter table public.controlai_members enable row level security;
alter table public.controlai_state enable row level security;
alter table public.controlai_audit enable row level security;
revoke all on public.controlai_members,public.controlai_state,public.controlai_audit from anon,authenticated;

create or replace function public.controlai_require_user() returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare m public.controlai_members; u auth.users;
begin
  select * into u from auth.users where id=auth.uid() and email_confirmed_at is not null;
  if u.id is null then raise sqlstate 'PT401' using message='Entre com uma conta de e-mail confirmada.'; end if;
  select * into m from public.controlai_members where email=lower(u.email) and active for update;
  if m.email is null or (m.user_id is not null and m.user_id<>u.id) then
    raise sqlstate 'PT403' using message='Esta conta não tem acesso ao ControlAI.';
  end if;
  if m.user_id is null then update public.controlai_members set user_id=u.id where email=m.email; end if;
  return jsonb_build_object('id',u.id,'nome',m.name,'email',m.email,'papel',m.role);
end $$;

create or replace function public.controlai_me() returns jsonb
language sql security definer set search_path=public,pg_temp as $$
  select public.controlai_require_user();
$$;

create or replace function public.controlai_read_state(p_backup boolean default false) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare actor jsonb; result jsonb;
begin
  actor:=public.controlai_require_user();
  if p_backup and actor->>'papel'<>'admin' then raise sqlstate 'PT403' using message='Apenas administrador.'; end if;
  select jsonb_build_object('revision',revision,'state',payload) into result from public.controlai_state where id=1;
  return result;
end $$;

create or replace function public.controlai_write_state(p_revision bigint,p_state jsonb,p_restore boolean default false) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare actor jsonb; old_state jsonb; new_state jsonb:=p_state; version bigint;
  kind text; row_data jsonb; prior jsonb; old_row jsonb; new_rows jsonb;
  line jsonb; delivery jsonb; total numeric; changes jsonb:='[]'; ids text[];
  stripped_old jsonb; stripped_new jsonb;
begin
  -- Ordem de locks consistente com gestão de usuários.
  perform pg_advisory_xact_lock(74291031);
  actor:=public.controlai_require_user();
  if p_restore and actor->>'papel'<>'admin' then raise sqlstate 'PT403' using message='Apenas administrador pode restaurar.'; end if;
  select payload,revision into old_state,version from public.controlai_state where id=1 for update;
  if p_revision is null or version<>p_revision then raise sqlstate 'PT409' using message='Outra sessão alterou os dados. Recarregue a página.'; end if;
  if jsonb_typeof(new_state) is distinct from 'object' then raise exception 'Estado inválido'; end if;
  foreach kind in array array['estoque','obras','itens'] loop
    if jsonb_typeof(new_state->kind) is distinct from 'array' then raise exception 'Lista inválida: %',kind; end if;
  end loop;
  foreach kind in array array['obras','itens','pedidos','entregas'] loop
    if not(new_state ? kind) then new_state:=jsonb_set(new_state,array[kind],'[]'); end if;
    if jsonb_typeof(new_state->kind) is distinct from 'array' then raise exception 'Lista inválida'; end if;
    ids:=array[]::text[]; new_rows:='[]';
    for row_data in select value from jsonb_array_elements(new_state->kind) loop
      if jsonb_typeof(row_data) is distinct from 'object' or jsonb_typeof(row_data->'id') not in ('string','number') or row_data->>'id' is null then raise exception 'Identificador inválido'; end if;
      if row_data->>'id'=any(ids) then raise exception 'Identificador duplicado'; end if;
      ids:=array_append(ids,row_data->>'id');
      select value into prior from jsonb_array_elements(coalesce(old_state->kind,'[]')) where value->>'id'=row_data->>'id';
      stripped_new:=row_data-array['criadoPor','atualizadoPor','registradoEmServidor'];
      stripped_old:=prior-array['criadoPor','atualizadoPor','registradoEmServidor'];
      if not p_restore and prior is not null then
        if kind='entregas' and stripped_new<>stripped_old then raise exception 'Entregas não podem ser editadas'; end if;
        if kind='pedidos' then
          if (stripped_new-'linhas')<>(stripped_old-'linhas') or not ((row_data->'linhas') @> (prior->'linhas')) then raise exception 'Preserve os dados históricos do pedido'; end if;
        end if;
      end if;
      if stripped_new is distinct from stripped_old or p_restore then
        row_data:=stripped_new||jsonb_build_object('criadoPor',coalesce(prior->'criadoPor',actor-'papel'),'atualizadoPor',actor-'papel','registradoEmServidor',coalesce(prior->'registradoEmServidor',to_jsonb(extract(epoch from now())::bigint)));
        changes:=changes||jsonb_build_array(jsonb_build_object('tipo',kind,'id',row_data->>'id','acao',case when prior is null then 'criado' else 'alterado' end));
      else row_data:=prior;
      end if;
      new_rows:=new_rows||jsonb_build_array(row_data);
    end loop;
    for old_row in select value from jsonb_array_elements(coalesce(old_state->kind,'[]')) loop
      if not(old_row->>'id'=any(ids)) then
        if not p_restore and kind in ('pedidos','entregas') then raise exception 'Histórico não pode ser excluído'; end if;
        changes:=changes||jsonb_build_array(jsonb_build_object('tipo',kind,'id',old_row->>'id','acao','removido'));
      end if;
    end loop;
    new_state:=jsonb_set(new_state,array[kind],new_rows);
  end loop;
  for row_data in select value from jsonb_array_elements(new_state->'pedidos') loop
    if jsonb_typeof(row_data->'linhas') is distinct from 'array' then raise exception 'Itens inválidos'; end if;
    if jsonb_array_length(row_data->'linhas')=0 then raise exception 'Pedido vazio'; end if;
    ids:=array[]::text[];
    for line in select value from jsonb_array_elements(row_data->'linhas') loop
      if line->>'id' is null or line->>'id'=any(ids) or jsonb_typeof(line->'qtd') is distinct from 'number' or (line->>'qtd')!~'^[1-9][0-9]*$' then raise exception 'Item ou quantidade inválida'; end if;
      ids:=array_append(ids,line->>'id');
    end loop;
  end loop;
  for delivery in select value from jsonb_array_elements(new_state->'entregas') loop
    if jsonb_typeof(delivery->'qtd') is distinct from 'number' or (delivery->>'qtd')!~'^[1-9][0-9]*$' then raise exception 'Quantidade entregue inválida'; end if;
    select l.value into line from jsonb_array_elements(new_state->'pedidos') p,
      lateral jsonb_array_elements(p.value->'linhas') l
      where p.value->>'id'=delivery->>'pedidoId' and l.value->>'id'=delivery->>'linhaId';
    if line is null then raise exception 'Entrega sem pedido correspondente'; end if;
    select sum((e.value->>'qtd')::numeric) into total from jsonb_array_elements(new_state->'entregas') e
      where e.value->>'pedidoId'=delivery->>'pedidoId' and e.value->>'linhaId'=delivery->>'linhaId';
    if total>(line->>'qtd')::numeric then raise exception 'Entrega excede a quantidade pendente'; end if;
  end loop;
  if old_state->'estoque' is distinct from new_state->'estoque' then
    changes:=changes||jsonb_build_array(jsonb_build_object('tipo','estoque','acao','importado','quantidade',jsonb_array_length(new_state->'estoque')));
  end if;
  update public.controlai_state set payload=new_state,revision=version+1 where id=1;
  insert into public.controlai_audit(user_id,actor,action,details) values
    (auth.uid(),actor->>'nome',case when p_restore then 'backup_restaurado' else 'dados_atualizados' end,jsonb_build_object('revisao',version+1,'alteracoes',changes));
  return jsonb_build_object('revision',version+1,'state',new_state);
end $$;

create or replace function public.controlai_list_users() returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare actor jsonb; result jsonb;
begin
  actor:=public.controlai_require_user();
  if actor->>'papel'<>'admin' then raise sqlstate 'PT403' using message='Apenas administrador.'; end if;
  select coalesce(jsonb_agg(jsonb_build_object('id',email,'nome',name,'email',email,'papel',role,'ativo',active,'pendente',user_id is null) order by role,email),'[]') into result from public.controlai_members;
  return jsonb_build_object('users',result,'invitations','[]'::jsonb);
end $$;

create or replace function public.controlai_manage_user(p_email text,p_name text default null,p_active boolean default true) returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare actor jsonb; target public.controlai_members; normalized text:=lower(trim(p_email)); slots integer;
begin
  perform pg_advisory_xact_lock(74291031);
  actor:=public.controlai_require_user();
  if actor->>'papel'<>'admin' then raise sqlstate 'PT403' using message='Apenas administrador.'; end if;
  if normalized is null or normalized!~'^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' or length(normalized)>254 then raise exception 'E-mail inválido'; end if;
  select * into target from public.controlai_members where email=normalized for update;
  if target.role='admin' then raise exception 'Preserve a conta do administrador'; end if;
  select count(*) into slots from public.controlai_members where active and email<>normalized;
  if p_active and slots>=3 then raise exception 'Limite de três acessos ativos'; end if;
  if target.email is null then
    if p_name is null or length(trim(p_name)) not between 1 and 150 then raise exception 'Nome inválido'; end if;
    insert into public.controlai_members(email,name,role,active) values(normalized,trim(p_name),'operador',p_active);
  else update public.controlai_members set active=p_active where email=normalized;
  end if;
  insert into public.controlai_audit(user_id,actor,action,details) values(auth.uid(),actor->>'nome','acesso_alterado',jsonb_build_object('email',normalized,'ativo',p_active));
  return jsonb_build_object('ok',true,'mode','supabase','message','Acesso autorizado. Crie esta conta em Supabase → Authentication → Users → Add user → Create new user. A pessoa deverá entrar com esse mesmo e-mail. Nenhum e-mail foi enviado.');
end $$;

create or replace function public.controlai_get_audit() returns jsonb
language plpgsql security definer set search_path=public,pg_temp as $$
declare actor jsonb; result jsonb;
begin
  actor:=public.controlai_require_user();
  if actor->>'papel'<>'admin' then raise sqlstate 'PT403' using message='Apenas administrador.'; end if;
  select coalesce(jsonb_agg(jsonb_build_object('id',id,'em',extract(epoch from at)::bigint,'usuario',actor_name,'acao',action,'detalhes',details) order by id desc),'[]') into result
  from (select a.id,a.at,a.actor as actor_name,a.action,a.details from public.controlai_audit a order by a.id desc limit 100) records;
  return jsonb_build_object('registros',result);
end $$;

revoke all on function public.controlai_require_user() from public,anon,authenticated;
revoke all on function public.controlai_me() from public,anon,authenticated;
revoke all on function public.controlai_read_state(boolean) from public,anon,authenticated;
revoke all on function public.controlai_write_state(bigint,jsonb,boolean) from public,anon,authenticated;
revoke all on function public.controlai_list_users() from public,anon,authenticated;
revoke all on function public.controlai_manage_user(text,text,boolean) from public,anon,authenticated;
revoke all on function public.controlai_get_audit() from public,anon,authenticated;
grant execute on function public.controlai_me(),public.controlai_read_state(boolean),public.controlai_write_state(bigint,jsonb,boolean),public.controlai_list_users(),public.controlai_manage_user(text,text,boolean),public.controlai_get_audit() to authenticated;
notify pgrst,'reload schema';
commit;
