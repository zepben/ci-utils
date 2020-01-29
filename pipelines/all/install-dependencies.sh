sed -i 's|http://|http://au.|g' /etc/apt/sources.list
apt-get update
# Tools
apt-get install --no-install-recommends openssh-client -y
apt-get install --no-install-recommends git -y
apt-get install --no-install-recommends wget -y
apt-get install --no-install-recommends curl -y
apt-get install --no-install-recommends xmlstarlet -y
apt-get install --no-install-recommends unzip -y
apt-get install --no-install-recommends jq -y
apt-get install --no-install-recommends software-properties-common -y
# Python
apt-get install --no-install-recommends gcc -y
apt-get install --no-install-recommends python3 -y
apt-get install --no-install-recommends python3-distutils -y
ln -s /usr/bin/python3 /usr/bin/python
wget https://bootstrap.pypa.io/get-pip.py -O - | python
python -m pip install twine
python -m pip install pytest
# Java - Amazon Corretto
apt-get install --no-install-recommends -y gnupg2
wget https://apt.corretto.aws/corretto.key -O- | apt-key add -
add-apt-repository 'deb https://apt.corretto.aws stable main'
apt-get update
apt-get install --no-install-recommends -y java-11-amazon-corretto-jdk
# dotnet core
wget -q https://packages.microsoft.com/config/ubuntu/19.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
dpkg -i packages-microsoft-prod.deb
apt-get update
apt-get install --no-install-recommends -y apt-transport-https
apt-get update
apt-get install --no-install-recommends -y dotnet-sdk-3.1
rm -f packages-microsoft-prod.deb
mkdir -p /root/.dotnet

apt-get clean