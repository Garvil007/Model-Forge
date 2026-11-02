# ModelForge API Lambda image. FastAPI via Mangum, packaged as a container image because
# apps/api depends on packages/catalog and packages/db — editable installs that aren't on
# PyPI, which the zip-based Lambda packaging story can't express cleanly.
#
# Build from the repo root (needs packages/catalog, packages/db and apps/api):
#   docker build -f apps/api/Dockerfile -t modelforge/api:dev .

FROM public.ecr.aws/lambda/python:3.12

COPY packages/catalog ${LAMBDA_TASK_ROOT}/packages/catalog
COPY packages/db ${LAMBDA_TASK_ROOT}/packages/db
COPY apps/api ${LAMBDA_TASK_ROOT}/app_src

RUN pip install --no-cache-dir \
      ${LAMBDA_TASK_ROOT}/packages/catalog \
      ${LAMBDA_TASK_ROOT}/packages/db \
      ${LAMBDA_TASK_ROOT}/app_src \
 && cp -r ${LAMBDA_TASK_ROOT}/app_src/app ${LAMBDA_TASK_ROOT}/app \
 && rm -rf ${LAMBDA_TASK_ROOT}/app_src ${LAMBDA_TASK_ROOT}/packages

CMD ["app.main.handler"]
