default: test

test: 
	cp -r ../templates/* site-config/
	./site-config/build.sh

clean:
	cd site-config; rm -rf docs version* package* docusaurus* node_modules build* tsconfig.json src
