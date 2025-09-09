default: test

test: 
	cp -r ../templates/* site-config/
	./site-config/build.sh

clean:
	rm -rf site-config/docs site-config/version*
	rm -rf site-config/package* site-config/docusaurus* site-config/node_modules site-config/build.sh site-config/tsconfig.json
