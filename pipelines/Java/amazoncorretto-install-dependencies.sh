yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm # for downloading xmlstarlet
yum install xmlstarlet -y
yum install jq -y
yum install zip gnupg python3 python3-pip -y
yum clean all
rm -rf /var/cache/yum

pip3 install --upgrade pip
# The upgrade will remove the pip3 binary and replace it with pip
pip install awscli

mkdir /maven