default: test

test: 
	cp -r ../templates/* site-config/
	./site-config/build.sh --skip-templates --skip-build

	cd site-config && npm ci && npm run build

clean:
	cd site-config; rm -rf docs version* package* docusaurus* node_modules build* run* tsconfig.json src
