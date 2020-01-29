apt-get update
apt-get install --no-install-recommends openssh-client -y
apt-get install --no-install-recommends git -y
apt-get install --no-install-recommends wget -y
apt-get install --no-install-recommends curl -y
apt-get install --no-install-recommends jq -y
python -m pip install twine
python -m pip install pytest

echo "alias build=\"bash /scripts/build.sh --python\"" >> ~/.bashrc
echo "alias release-lib=\"bash /scripts/release-lib.sh --python\"" >> ~/.bashrc
echo "alias update-version=\"bash /scripts/update-version.sh --python\"" >> ~/.bashrc
echo "alias finalize-version=\"bash /scripts/finalize-version.sh --python\"" >> ~/.bashrc