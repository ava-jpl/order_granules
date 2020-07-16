FROM hysds/pge-base:latest-es1
MAINTAINER torresal "alexander.p.torres@jpl.nasa.gov"
LABEL description="Order ASTER products from metadata"

USER ops

COPY . /home/ops/verdi/ops/order_granules

WORKDIR /home/ops
CMD ["/bin/bash", "--login"]

