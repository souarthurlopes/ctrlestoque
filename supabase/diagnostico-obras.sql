-- Diagnóstico somente de leitura: não modifica os registros.
-- Execute no SQL Editor se o cadastro ainda falhar após atualizar o app.
with estado as (
  select payload from public.controlai_state where id=1
), registros as (
  select o.value->>'id' as id from estado,
    lateral jsonb_array_elements(payload->'obras') o
), ids as (
  select r.id from registros r
  union all
  select i.value->>'id' from estado,
    lateral jsonb_array_elements(payload->'itens') i
)
select
  (select payload->>'nid' from estado) as contador_atual,
  (select max(case when id~'^[0-9]+$' then id::numeric end) from ids) as maior_identificador,
  (select count(*)-count(distinct id) from registros) as ids_de_obras_duplicados,
  has_function_privilege('authenticated','public.controlai_write_state(bigint,jsonb,boolean)','execute') as funcao_pode_ser_chamada,
  (select prosecdef from pg_proc where oid='public.controlai_write_state(bigint,jsonb,boolean)'::regprocedure) as funcao_com_permissao_propria,
  position('row_data->''linhas'' @> prior->''linhas''' in pg_get_functiondef('public.controlai_write_state(bigint,jsonb,boolean)'::regprocedure))>0 as funcao_com_comparacao_antiga;
