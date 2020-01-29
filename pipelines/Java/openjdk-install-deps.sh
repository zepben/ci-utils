export MAVEN_VERSION=3.6.3
export MAVEN_ARCHIVE=http://apache.osuosl.org/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz
apk --update add --no-cache tzdata bash wget curl tar zip jq xmlstarlet
wget ${MAVEN_ARCHIVE}
tar -xf apache-maven-${MAVEN_VERSION}-bin.tar.gz -C /usr/local
mv /usr/local/apache-maven-${MAVEN_VERSION} /usr/local/maven
rm apache-maven-${MAVEN_VERSION}-bin.tar.gz
mkdir -p /usr/share/maven/conf