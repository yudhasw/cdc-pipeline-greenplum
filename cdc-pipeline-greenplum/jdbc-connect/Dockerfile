FROM quay.io/debezium/connect:2.7

USER root

ENV JDBC_CONNECTOR_VERSION=10.7.4

# Install plugin kafka-connect-jdbc (Confluent Community License)
RUN microdnf install -y unzip curl && microdnf clean all && \
    mkdir -p /kafka/connect/kafka-connect-jdbc && \
    curl -fsSL -o /tmp/jdbc.zip \
      "https://hub-downloads.confluent.io/api/plugins/confluentinc/kafka-connect-jdbc/versions/${JDBC_CONNECTOR_VERSION}/confluentinc-kafka-connect-jdbc-${JDBC_CONNECTOR_VERSION}.zip" && \
    cd /tmp && unzip -q jdbc.zip && \
    find /tmp -iname "*.jar" -path "*lib*" -exec cp {} /kafka/connect/kafka-connect-jdbc/ \; && \
    rm -rf /tmp/jdbc.zip /tmp/confluentinc-kafka-connect-jdbc-*

USER kafka
