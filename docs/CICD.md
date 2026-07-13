# CI/CD avanzado (Prompt 22)

Workflow: `.github/workflows/ci-advanced.yml`

## Etapas

1. Format / lint / types  
2. Unit + coverage gates (`scripts/ci/check_coverage_gates.py`)  
3. Integration + contract  
4. E2E + regression + resilience + performance + stress  
5. Security tests + dependency/secret scan + SBOM stub  
6. Infra validate (Terraform)  
7. Frontend build  
8. Build artifacts + version manifest  
9. Deploy: dev automático → staging aprobación → prod doble aprobación  

## Quality gates

- Fallo de tests  
- Cobertura bajo umbral (dominio/risk/pricing/api/total)  
- Secretos heurísticos  
- Snapshots de regresión sin aceptación  
- Cambios críticos requieren review (ver `CODEOWNERS`)

## Worker

Ver `scripts/ci/worker_safe_deploy.md` y `scripts/ci/rollback.md`.
