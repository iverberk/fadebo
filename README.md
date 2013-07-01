# Fabric Deployment Boilerplate

* Website: [http://www.ivoverberk.nl/blog/2013/06/23/application-deployment-with-fabric](http://www.ivoverberk.nl/blog/2013/06/23/application-deployment-with-fabric)

Fabric Deployment Boilerplate (FaDeBo) provides a boilerplate deployment script structure based on the Fabric library.
It it supposed to be a drop-in solution for automating application deployments. Only a minimal amount of setting need to
be configured to generate a fully working deployment solution. At the same time it leaves enough extensions points to easily
add your own customizations.

## Usage

The deployment script is run with following command line:

```
  fab {$env} {deploy,rollback}
```

This will either deploy or rollback the code on {$env}. Out of the box three environments are supported: test, staging and production.
More environments can be added to the script if you need them. A deployment command would look like:

```
  fab production deploy
```

It is possible to run the script in automated mode. This means that no questions will be asked. If the deployment fails at any stage it will
automatically roll back the deployment. It will also automatically bootstrap the target environment if it has not been bootstrapped previously.

```
  fab staging deploy:auto_mode=yes
```

Depending on the deployment method (see below) you can also specify a revision or version of the application to be deployed.

```
  fab test deploy:develop,auto_mode=yes
```

This will deploy the 'develop' branch in a GIT repository.

```
  fab production deploy:version=1.0.0
```

You can use the version paramater to locate the correct version of your remote package for example (e.g. grab 1.0.0 from the Nexus release artifact).

## Bootstrapping

Running the deployment for the first time will bootstrap the target environment. This basically creates the following directory structure
on your environment:

```
app\_dir/

  /src
  /releases
  /tools
  /shared
```

* The 'src' directory is used for any libraries that can not be retrieved with a package management system. 
* The 'releases' directory will contain timestamped deployment directories and a 'current' symlink, which will always point to the last deployment directory. 
At most five releases will be kept on the environment (this is configurable). 
* The 'tools' directory might contain any tools that are needed by the application and finally
* the 'shared' directory will contain all the files that need to be shared by all releases. All environment sensitive data, like db passwords etc.,
need to be in this directory. The files will be symlinked into the release directory by the deployment script according to the settings file.

## Settings

Every environment needs a settings.py file. A sample settings.py.example file is included in the repository. Most settings are pretty self-explantory
and are documented in the code. The symlinks variable expects a hash of source and target files. For example, to include the db.php file in the shared
folder into the config/ directory of your application you would enter the following values:

```
'symlinks' : {
  'shared/db.php': 'config/db.php'
}
```

The source file/directory will always be relative to your application directory (app\_dir) and the target file/directory will be relative to the release
directory. It is possible to use the release directory in your source specification by using {release\_dir} (e.g. '{release\_dir}/tomcat').

## Deployment Methods

FaDeBo understands three deployment methods.

* GIT: in the settings you can specify a git repository to be used for deployment. If you want to package from the local repository you must add a '.' .
This is useful if your application is checked out by a build server. This method creates a tar.gz file from the specified revision and sends this file to
the remote environment for further processing.
* Package: you can specify the location of a package on a remote location. This will download the package on the remote server and extract it for further
processing. This can be used for example to grab release artifacts from Nexus. Authentication for the remote location needs to be implemented :-)
* Artifacts: In the settings file you can specify local artifacts that need to be copied to the target environment. This simply grabs the files/directories
you specify and puts them in the remote location. The 'artifacts' expects a hash in the same manner as the 'symlinks' variable.
