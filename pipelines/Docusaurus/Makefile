# This is for local testing
current_dir:=${CURDIR}
targets = doctest

doctest: clean
    # Build with self but overwrite the project files from this branch
	podman run --rm \
		-v ${current_dir}/templates:/templates \
		-v ${current_dir}/docs:/docs \
	    -v ~/.npmrc:/root/.npmrc \
		-it localhost/test \
		/templates/build-docs.sh

clean:
	# Clear all the files
	for f in "./docs/package.json" "./docs/package-lock.json" "./docs/src" "./docs/docusaurus.config.js" "./docs/tsconfig.json"; do \
		rm -rf $$f; \
	done
