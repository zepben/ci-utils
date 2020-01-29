echo "alias cs-build=\"bash /scripts/build.sh --csharp\"" >> ~/.bashrc
echo "alias cs-deploy=\"bash /scripts/release-lib.sh --csharp\"" >> ~/.bashrc
echo "alias cs-update-version=\"bash /scripts/update-version.sh --csharp --no-commit\"" >> ~/.bashrc
echo "alias cs-finalize-version=\"bash /scripts/finalize-version.sh --csharp --no-commit\"" >> ~/.bashrc

echo "alias java-gradle-build=\"bash /scripts/build.sh --java --gradle\"" >> ~/.bashrc
echo "alias java-gradle-deploy=\"bash /scripts/release-lib.sh --java --gradle\"" >> ~/.bashrc
echo "alias java-gradle-update-version=\"bash /scripts/update-version.sh --java --gradle --no-commit\"" >> ~/.bashrc
echo "alias java-gradle-finalize-version=\"bash /scripts/finalize-version.sh --java --gradle --no-commit\"" >> ~/.bashrc

echo "alias py-deploy=\"bash /scripts/release-lib.sh --python\"" >> ~/.bashrc
echo "alias py-update-version=\"bash /scripts/update-version.sh --python --no-commit\"" >> ~/.bashrc
echo "alias py-finalize-version=\"bash /scripts/finalize-version.sh --python --no-commit\"" >> ~/.bashrc