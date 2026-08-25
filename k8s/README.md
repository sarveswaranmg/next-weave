# Deploying NeuroWeave on Kubernetes

These manifests were verified end-to-end against a local `kind` cluster (Docker Desktop, no
cloud account needed) as part of hardening this repo for production use. This doc captures
exactly what that verification covered, what it couldn't cover locally, and how to reproduce or
extend it against a real cluster.

## Prerequisites

- A running cluster and `kubectl` context pointed at it.
- [cert-manager](https://cert-manager.io/docs/installation/) installed cluster-wide, if you're
  using `ingress.yaml`'s TLS (not provisioned by these manifests - a one-time cluster setup step).
- [metrics-server](https://github.com/kubernetes-sigs/metrics-server) installed, or the two
  `HorizontalPodAutoscaler` objects will accept but never act on CPU/memory metrics (`<unknown>`
  forever). Most managed Kubernetes services (EKS, GKE, AKS) ship this by default; `kind`/
  `minikube` do not.
- A real Postgres+pgvector and Redis reachable from the cluster (managed RDS/Cloud SQL +
  ElastiCache/Memorystore in production - see the comment in `configmap.yaml`). These manifests
  intentionally don't include Postgres/Redis Deployments - that's an operational choice, not an
  oversight.

## Deploy order

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
# Fill in k8s/secret.example.yaml -> k8s/secret.yaml (gitignored, never commit it) and:
kubectl apply -f k8s/secret.yaml
# Or, preferably, create the Secret imperatively so real values never touch a file on disk/in git:
#   kubectl create secret generic neuroweave-secrets -n neuroweave \
#     --from-literal=DATABASE_URL=... --from-literal=OPENAI_API_KEY=... \
#     --from-literal=RUNTIME_API_KEY=... \
#     --from-literal=CREDENTIAL_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Substitute a real image tag before applying (see the comment in api-deployment.yaml):
sed -i "s|neuroweave:IMAGE_TAG|neuroweave:${GIT_SHA}|" k8s/api-deployment.yaml k8s/worker-deployment.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml

# Run the migration once, against whichever image/tag you just deployed:
kubectl run migrate --image=neuroweave:${GIT_SHA} -n neuroweave --restart=Never \
  --command -- alembic -c migrations/alembic.ini upgrade head
kubectl logs -n neuroweave migrate   # confirm it reached "011 (head)" with no errors
kubectl delete pod -n neuroweave migrate

# Bootstrap your first tenant + API key:
kubectl run bootstrap --image=neuroweave:${GIT_SHA} -n neuroweave --restart=Never -it --rm \
  --command -- python scripts/bootstrap_tenant.py --name "My Company" --email me@example.com

kubectl apply -f k8s/ingress.yaml   # only if cert-manager is installed (see below)
```

## What was actually verified locally (`kind`), and how

1. `brew install kind && kind create cluster --name neuroweave-verify`
2. `docker build -t neuroweave:verify .` then `kind load docker-image neuroweave:verify --name neuroweave-verify`
   (makes a locally-built image available inside the cluster without a registry).
3. Installed `metrics-server` and patched it with `--kubelet-insecure-tls` (a `kind`-specific
   requirement for its self-signed kubelet certs - not needed on a real managed cluster).
4. Applied `namespace.yaml`, `configmap.yaml`, a filled-in secret, plus throwaway Postgres+Redis
   Deployments (not part of this directory - real deployments use managed services per above).
5. Ran `alembic -c migrations/alembic.ini upgrade head` as a one-off pod against that Postgres -
   this is what caught two real, previously-undetected bugs: `migrations/alembic.ini` was missing
   its `[alembic]` section entirely (migrations had *never* actually run via the CLI in this
   project's history - CI only ever did `Base.metadata.create_all()` directly), and the Docker
   image had no `PYTHONPATH`, so `alembic` couldn't import `neurowave_engine.core.config` from inside the
   container. Both are fixed now (see `migrations/alembic.ini` and the `Dockerfile`).
6. Applied `api-deployment.yaml` and `worker-deployment.yaml` (with the image tag substituted) and
   confirmed: pods reach `Running`/`Ready` (validates the readiness/liveness probe paths actually
   respond - `/runtime/health` is deliberately unauthenticated for exactly this reason), both
   `HorizontalPodAutoscaler` objects are accepted by the API server *and* report real utilization
   (`cpu: 1%/70%, memory: 30%/80%` at idle - metrics-server genuinely working, not just
   structurally-valid-but-`<unknown>`), and `neuroweave-celery-beat` runs as the intended singleton
   (`replicas: 1`, matching its own comment about not double-firing scheduled tasks).
   This step caught a real, previously-undetected bug: `app/workers/__init__.py` eagerly imported a
   task function (`consolidate_similar_memories`) that doesn't exist in `app/workers/tasks.py` (the
   real name is `consolidate_user_memories_task`) - the celery worker and beat containers
   crash-looped on startup with `ImportError` until this was fixed. Nothing in the existing test
   suite or CI ever actually started a celery worker process, so this had never surfaced before.
7. Torn down (`kind delete cluster --name neuroweave-verify`) - this was a throwaway cluster, not
   a persistent environment.

## What was **not** verified locally, and why

- **TLS via `ingress.yaml`'s cert-manager annotation.** This needs (a) cert-manager actually
  installed cluster-wide, and (b) a real, publicly-resolvable domain reachable from the internet
  for Let's Encrypt's HTTP-01/DNS-01 challenge - neither is achievable from a sandboxed local
  `kind` cluster with no public ingress. The Ingress YAML itself was confirmed structurally valid
  (accepted by the API server, correct annotation keys), but the TLS handshake was not exercised.
  When you deploy to a real cluster: point the `host` at a domain you own, install cert-manager,
  and test against the `letsencrypt-staging` `ClusterIssuer` first (higher rate limits, untrusted
  cert) before switching the annotation to `letsencrypt-prod`.
- **Real autoscaling behavior.** The HPA objects are structurally valid and metrics-server reports
  utilization, but nothing in this pass generated enough load to trigger an actual scale-up/down -
  that requires a real load test, which wasn't part of this exercise.
- **Celery beat's actual scheduling behavior under a real broker.** The singleton replica count is
  correct by inspection, but confirming "a second beat process double-fires tasks" would require
  deliberately misconfiguring it and watching a task fire twice - not attempted here, since the
  point was verifying the *documented* configuration, not the failure mode it avoids.

## Secrets management

Three tiers, cheapest-first:

1. **Now, zero infra dependency:** never `kubectl apply -f` a filled-in secret YAML - `k8s/secret.yaml`
   is gitignored precisely so the real values never touch git history. Generate the Secret
   imperatively instead (`kubectl create secret generic ...`, see "Deploy order" above) - the
   values then only ever exist in your shell history and the cluster's etcd, not a file on disk.
2. **If you add CI/CD deploys:** store the real values as encrypted CI secrets (e.g. GitHub Actions
   repo/environment secrets - already trusted, zero new infra) and have the deploy job run the same
   `kubectl create secret generic ... --from-literal=X=${{ secrets.X }}` command at deploy time.
   Secrets then live in the CI provider's secret store and the cluster's etcd only - never in a
   YAML file, never in git.
3. **Once you provision real cloud infra:** move to the External Secrets Operator (ESO) pointed at
   whichever managed secret store your cloud provides (AWS Secrets Manager, GCP Secret Manager,
   Vault) - ESO syncs from the real secret manager into a `Secret` object automatically. This is
   the target end-state but deliberately not built now: it needs an actual cloud account/IAM setup
   this repo has no way to provision or verify.

Encryption at rest for etcd itself is a cluster-level setting (on by default on most managed
control planes - EKS/GKE; opt-in on self-managed clusters) - an operator checklist item for
whichever managed Kubernetes service you choose, not something these manifests can enforce.

`CREDENTIAL_ENCRYPTION_KEY` and `DATABASE_URL`/`DATABASE_PASSWORD` are the remaining global
secrets after the multi-tenant auth work (see the main README's "Multi-Tenancy & Auth" section) -
per-tenant `ApiKey` rows are individually revocable, so there's no single shared auth secret left
to rotate the way `RUNTIME_API_KEY` used to be.

## Image tag / per-environment overlays

There's no Helm chart or Kustomize overlay here - the YAML is static. If you need per-environment
(staging/prod) differences beyond swapping the image tag, adopt Kustomize
(`kustomize edit set image`, `overlays/staging`, `overlays/prod`) rather than hand-editing these
files per deploy.
