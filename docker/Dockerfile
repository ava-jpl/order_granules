FROM hysds/pge-base:latest-es1
MAINTAINER torresal "alexander.p.torres@jpl.nasa.gov"
LABEL description="Order ASTER products from metadata"

USER ops

COPY . /home/ops/verdi/ops/order_granules
RUN set -ex \
    && sudo chown -R ops:ops /home/ops/verdi/ops/order_granules \
    && pip install xmltodict

WORKDIR /home/ops
CMD ["/bin/bash", "--login"]

