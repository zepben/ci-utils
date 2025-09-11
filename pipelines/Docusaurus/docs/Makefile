default: test

test: 
	cp -r ../templates/* site-config/
	./site-config/build.sh --skip-build
	cd site-config; cat package.json; cat docusaurus.config.js; npm run build

clean:
	cd site-config; rm -rf docs version* package* docusaurus* node_modules build* tsconfig.json src
