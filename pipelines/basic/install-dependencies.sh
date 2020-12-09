apk add --no-cache --update
apk add --no-cache tzdata
apk add --no-cache git
apk add --no-cache xmlstarlet
apk add --no-cache openssh-client
apk add --no-cache curl
apk add --no-cache zip
apk add --no-cache jq
apk add --no-cache python3 py3-pip
apk add --no-cache gnupg
apk add --no-cache --upgrade bash

pip3 install --upgrade pip
pip3 install awscli

cat > /scripts/.bashrc << EOF
alias release-checks="bash /scripts/release-checks.sh";
alias create-branch="bash /scripts/create-branch.sh";
alias rebase="bash /scripts/rebase-onto-release.sh";
alias azure-devops="bash /scripts/trigger-azure-devops.sh";
alias gh-action="bash /scripts/trigger-gh-action.sh";
alias release-docs-source="bash /scripts/release-docs-source.sh";
alias cs-release-checks="bash /scripts/release-checks.sh --csharp";
alias cs-update-version="bash /scripts/update-version.sh --csharp";
alias cs-finalize-version="bash /scripts/finalize-version.sh --csharp";
alias js-release-checks="bash /scripts/release-checks.sh --js";
alias js-update-version="bash /scripts/update-version.sh --js";
alias js-finalize-version="bash /scripts/finalize-version.sh --js";
alias java-mvn-release-checks="bash /scripts/release-checks.sh --java --maven";
alias java-mvn-update-version="bash /scripts/update-version.sh --java --maven";
alias java-mvn-finalize-version="bash /scripts/finalize-version.sh --java --maven";
alias java-mvn-check-release-version="bash /scripts/check-release-version.sh --java --maven";
alias java-gradle-release-checks="bash /scripts/release-checks.sh --java --gradle";
alias java-gradle-update-version="bash /scripts/update-version.sh --java --gradle";
alias java-gradle-finalize-version="bash /scripts/finalize-version.sh --java --gradle";
alias py-release-checks="bash /scripts/release-checks.sh --python";
alias py-update-version="bash /scripts/update-version.sh --python";
alias py-finalize-version="bash /scripts/finalize-version.sh --python";
EOF

cp /scripts/.bashrc ~/.bashrc