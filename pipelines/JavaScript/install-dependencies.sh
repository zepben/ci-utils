apk add --no-cache --update
apk add --no-cache tzdata
apk add --no-cache zip
apk add --no-cache jq
apk add --no-cache git
apk add --no-cache curl
apk add --no-cache --upgrade bash

echo "alias release-app=\"bash /scripts/release-app.sh --js\"" >> ~/.bashrc
echo "alias build=\"bash /scripts/build.sh --js\"" >> ~/.bashrc
echo "alias release-lib=\"bash /scripts/release-lib.sh --js\"" >> ~/.bashrc