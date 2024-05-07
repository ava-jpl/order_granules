FROM hysds/pge-base:develop-es1
MAINTAINER torresal "alexander.p.torres@jpl.nasa.gov"
LABEL description="Order ASTER products from metadata"

USER ops

COPY . /home/ops/verdi/ops/order_granules
RUN set -ex \
    && sudo chown -R ops:ops /home/ops/verdi/ops/order_granules \
    && /home/ops/verdi/bin/pip install xmltodict \
    && /home/ops/verdi/bin/pip install pandas \

WORKDIR /home/ops
CMD ["/bin/bash", "--login"]

