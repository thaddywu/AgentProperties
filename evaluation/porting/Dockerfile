FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libffi8 libgomp1 libncurses6 libsqlite3-0 util-linux mcpp \
    && rm -rf /var/lib/apt/lists/*
ADD https://github.com/souffle-lang/souffle/releases/download/2.5/x86_64-ubuntu-2204-souffle-2.5-Linux.deb /tmp/souffle.deb
RUN echo 'c21e2f8153c140499f5b2aa30a148dddec7be5663e36071466cdc225a6682f9fe699b939241c7c28258ee96d1e2c2fe5585e9e8e6b74fb20172f06d2b40774da  /tmp/souffle.deb' | sha512sum -c - \
    && dpkg-deb -x /tmp/souffle.deb /opt/souffle && rm /tmp/souffle.deb
ENV PATH="/opt/souffle/usr/bin:${PATH}" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY runtime/python/policy_runtime /framework/policy_runtime
COPY translation/python/policy_translation /framework/policy_translation
COPY query/python/policy_query /framework/policy_query
COPY evaluation/policy_evaluation /framework/policy_evaluation
ENV PYTHONPATH=/framework
WORKDIR /tmp
USER 65534:65534
ENTRYPOINT ["python", "-m", "policy_evaluation.porting.worker"]
