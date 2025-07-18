apt -y update && apt install --no-install-recommends -y wget gpg ca-certificates
wget -O - https://apt.corretto.aws/corretto.key | gpg --dearmor -o /usr/share/keyrings/corretto-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/corretto-keyring.gpg] https://apt.corretto.aws stable main" | tee /etc/apt/sources.list.d/corretto.list
wget -O /usr/share/keyrings/githubcli-archive-keyring.gpg https://cli.github.com/packages/githubcli-archive-keyring.gpg \
	&& chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
	&& echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list 

apt -y update && apt install --no-install-recommends -y \
 java-11-amazon-corretto-jdk \
 libxml2-utils \
 xmlstarlet \
 jq \
 gnupg \
 python3 \
 python3-pip \
 git \
 zip \
 curl \
 wget \
 awscli \
 gh \
 maven && rm -rf /var/lib/apt/lists/*

apt clean
rm -rf /usr/lib/jvm/java-11-amazon-corretto/lib/src.zip 

mkdir /maven
