apk add --no-cache --update
apk add --no-cache tzdata
apk add --no-cache git
apk add --no-cache xmlstarlet
apk add --no-cache curl
apk add --no-cache jq
apk add --no-cache --upgrade bash

echo "alias build=\"bash /scripts/build.sh --csharp\"" >> ~/.bashrc
echo "alias release-lib=\"bash /scripts/release-lib.sh --csharp\"" >> ~/.bashrc
echo "alias update-version=\"bash /scripts/update-version.sh --csharp\"" >> ~/.bashrc
echo "alias finalize-version=\"bash /scripts/finalize-version.sh --csharp\"" >> ~/.bashrc