# Fabric Deployment Boilerplate
# Author: Ivo Verberk
# 12-02-2013
#
# Description:
#
# This boilerplate script can be used as a skeleton to create deployment scripts for applications.
#
# Usage:
#
# From the command line run:
#
#   fab {test, staging, production} {deploy, rollback}
#
# Running the deploy command for the first time will automatically (or if you confirm) bootstrap your target environment
#

# Import functions from the Fabric API and Python libraries
from __future__ import with_statement
from fabric.api import *
from fabric.colors import red, green
from fabric.contrib.files import exists
from fabric.contrib.console import confirm
from contextlib import contextmanager, nested
import os, sys, getpass, datetime, StringIO

# This dict contains the states of the various deployment stages.
# These stages are used to determine what needs to be rolled back.
env.stages = {
  'start_deploy'  : False,
  'deployed_pkg'  : False,
  'migrated_db'   : False,
  'activated'     : False
}

##############################################################
#
# These tasks initialize the target environment for deployment
#
##############################################################

# Find all previous deployments
def get_releases():
  with settings(hide('running','stdout')):
    env.releases = sorted(run("ls -x %s/releases | sed 's/current//'" % env.app_dir).split())
    env.current_release = False
    env.previous_release = False

    if len(env.releases) >= 1:
      env.current_release = env.releases[-1]  # Identify the current release folder
    if len(env.releases) > 1:
      env.previous_release = env.releases[-2] # Identify the previous release folder

    if len(env.releases) > 0:
      if exists("%s/releases/current" % env.app_dir):
        if not env.current_release in run("readlink %s/releases/current" % env.app_dir):
          abort(red("The 'current' symlink does not match the latest release directory. Please check for a failed deployment!"))

# Checks if a previous bootstrap was performed and find releases
def env_check():
  bootstrap_file = "%s/.bootstrap" % env.app_dir
  env.bootstrapped = exists(bootstrap_file)

  get_releases()

# Initializes the test environment
@task
def test():
  sys.path.append(os.path.dirname(os.path.realpath(__file__)))

  from deploy.test import settings
  env.update(settings.context)
  env.environment = 'test'
  env_check()

# Initializes the staging environment
@task
def staging():
  sys.path.append(os.path.dirname(os.path.realpath(__file__)))

  from deploy.staging import settings
  env.update(settings.context)
  env.environment = 'staging'
  env_check()

# Initializes the production environment
@task
def production():
  sys.path.append(os.path.dirname(os.path.realpath(__file__)))

  from deploy.production import settings
  env.update(settings.context)
  env.environment = 'production'
  env_check()

########################################################################
#
# These functions are used for (re-)bootstrapping the target environment
#
########################################################################

# Creates the releases and shared directories
def create_directories():
  print green("=> create directories")
  run("mkdir -p {releases,shared,tools,src}")

# Install tools that are necessary for the application or deployment
def install_tools():
  print green("=> install required tools")
  with cd('tools'):
    pass

# Copy an arbitrary folder from the remote application to a local directory
# This can be used to create or alter files with sensitive data
@task
def get_folder(folder=None,purge='no'):
  require('environment', provided_by=[test, staging, production])

  if env.bootstrapped != True:
    abort(red("please bootstrap your environment first."))

  if folder != None:
    target = "%s/%s" % (env.env_dir, env.environment)
    source = "%s/%s" % (env.app_dir, folder)
    with settings(hide('running','stdout','warnings')):
      if purge == 'yes':
        print green("purge local folder")
        local("rm -rf %s/%s/*" % (target,folder))

      print green("=> getting contents of folder '%s'" % folder)
      get(source, target)
  else:
    abort(red("Please specify a folder to get."))

# Copy an arbitrary local folder to the remote application
# This can be used to create or alter files with sensitive data
@task
def put_folder(folder=None,purge='no'):
  require('environment', provided_by=[test, staging, production])

  if env.bootstrapped != True:
    abort(red("Please bootstrap your environment first"))

  if folder != None:
    source = "%s/%s/%s" % (env.env_dir, env.environment, folder)
    target = "%s/%s" % (env.app_dir, folder)
    with settings(hide('running','stdout','warnings')):
      if purge == 'yes':
        print green("purge remote folder")
        run("rm -rf %s/*" % target)

      print green("=> uploading contents of folder '%s'" % folder)
      put(source, env.app_dir)
  else:
    abort(red("Please specify a folder to put."))

# Bootstrap the environment so it can accept a deployment
def bootstrap(force='no'):
  require('environment', provided_by=[test, staging, production])

  print green("Bootstrapping the %s environment for application deployment..." % env.environment)

  if env.bootstrapped and not force == 'yes':
    abort(red("Environment already bootstrapped."))

  with nested(cd(env.app_dir), settings(hide('running','stdout'))):
    execute(create_directories)
    execute(install_tools)

    # At this stage we mark the bootstrap as completed
    env.bootstrapped = True
    run("touch .bootstrap")

  # Upload the default shared folder
  put_folder('shared')

########################################################
#
# These functions migrate the database during deployment
#
########################################################

# Migrate the database
def migrate_up():
  print green("=> migratng the database up")

  env.stages['migrated_db'] = True

def migrate_down():
  print green("=> migratng the database down")

####################################################
#
# These functions are used to deploy the application
#
####################################################

# This is a wrapper to make sure that errors during deployment steps are handled gracefully
@contextmanager
def failwrap():
  try:
    yield
  except SystemExit:
    run("rm -f .deploy_lock")
    if not env.auto_mode and not confirm(red("A deployment step failed. Would you like to revert the deployment?")):
      return

    rollback()

# Check that all prerequisites are valid
def check_prerequisites():
  print green("=> checking prerequisites")

  if env.bootstrapped != True:
    if env.auto_mode or confirm(green("This appears to be fresh deployment. Bootstrap your environment now?")):
      bootstrap()
    else:
      abort(red("You must bootstrap your environment before deployment."))

# Create a package from the git repository
def git_create_package():

  # Check if branch exists in repository
  with nested(settings(warn_only=True), hide('running','stderr', 'warnings')):
    if not local("git show-ref --verify --quiet refs/heads/%s" % env.branch).succeeded:
      abort(red("Could not find branch '%s' or command is not run in a git repository." % env.branch))

  # Archive a specified branch to a tar.gz archive
  local("git archive --format=tar --remote=%s %s | gzip -9 - > %s.tar.gz" % (env.repo, env.branch, env.release_name))

# Send a package to the remote server
def git_send_package():

  # Switch to the remote release directory and copy the archive, afterwards delete the archive
  run("mkdir %s" % env.release_dir)
  with cd(env.release_dir):
    put("%s.tar.gz" % env.release_name, '.')
    run("tar -xzmf %s.tar.gz" % env.release_name)
    run("rm %s.tar.gz" % env.release_name)

  # Delete the local archive
  local("rm %s.tar.gz" % env.release_name)

# Deploy a package on the remote server
def deploy_package():
  print green("=> deploying package on %s environment" % env.environment)

  # Deploy the artifacts
  for artifact in env.artifacts:
    put(artifact,env.artifacts[artifact])

  # Deploy from a remote package
  if env.package_url != '':
    print green("=> fetching package from '%s'" % env.package_url)

    if env.package_format == 'zip':
      run("wget %s -O %s.zip -q" % (env.package_url, env.release_name))
      run("unzip %s.zip -d %s" % (env.release_name, env.release_dir) )
      run("rm -f %s" % env.release_name)
    elif env.package_format == 'tar':
      run("wget %s -O- -q | tar xz -C %s" % (env.package_url, env.release_name))
    else:
      abort(red("Package format '%s' is not supported at this time." % env.package_format))

  # Deploy from a git repository
  elif env.repo != '':
    git_create_package()
    git_send_package()

  # Mark the deployment of the package
  env.stages['deployed_pkg'] = True

# Install all the dependencies that the application requires (composer, gem, etc.)
def resolve_dependencies():
  with cd(env.release_dir):
    pass

# Set correct permissions
def permissions():
  pass

# Start services on the remote server
def start_services():
  pass

# Stop services on the remote server
def stop_services():
  pass

# Create symlinks from shared folder 
def create_symlinks():
  for source,target in env.symlinks.iteritems():
    source = source.format(release_dir=env.release_dir)
    run("ln -s %s/%s %s/%s" % (env.app_dir, source, env.release_dir, target))

# Perform all steps before activation of the new release
def pre_activate():
  print green("=> preparing activation")
  execute(create_symlinks)
  execute(permissions)
  stop_services()

# Activate the new release
def activate():
  print green("=> activating the new release")

  env.previous_release = env.current_release
  run("ln -sfn %s/%s releases/current" % (env.release_name, env.public_dir))
  env.current_release = env.release_name

  env.stages['activated'] = True

# Cleans up the older releases according to the env.keep_releases setting
def cleanup_releases():

  num_releases = len(env.releases)
  if num_releases > env.keep_releases:
    print green("=> cleaning up old releases")

    for i in range(-num_releases, -env.keep_releases):
      run("rm -rf releases/%s" % env.releases[i])

# Perform all steps after activation of the new release
def post_activate():
  print green("=> finishing activation")
  start_services()
  cleanup_releases()

def smoke_test():
  pass

# Deploy application to the target environment
@task
def deploy(branch='master',auto_mode=False):
  require('environment', provided_by=[test, staging, production])

  print green("Deploying the application to the '%s' environment" % env.environment)

  # This variable indicates automatic mode deployment
  # No questions are asked in automatic mode and a failed deployment is rolled back automatically
  env.auto_mode = auto_mode
  env.branch = branch
  env.release_name = env.release_www = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
  env.release_dir = 'releases/' + env.release_name
  if env.public_dir != '':
    env.release_www += '/' + env.public_dir
  env.stages['start_deploy'] = True

  with nested(cd(env.app_dir), settings(hide('running','stdout'))):

    if exists('.deploy_lock'):
      abort(red('Found lock file. Please check if another deploy is running or previous deploy failed.'))

    run("touch .deploy_lock")
    # Execute all the deployment steps in order
    with failwrap():
      execute(check_prerequisites)
      execute(deploy_package)
      execute(resolve_dependencies)
      execute(migrate_up)
      execute(pre_activate)
      execute(activate)
      execute(post_activate)
      execute(smoke_test)
    run("rm -f .deploy_lock")

######################################################
#
# This functions is used to rollback the application
#
######################################################

@task
def rollback():
  require('environment', provided_by=[test, staging, production])

  print green("Rolling back to previous release")

  with nested(cd(env.app_dir), settings(hide('running','stdout'))):
    if env.bootstrapped == True:
      if env.stages['start_deploy'] == False:
        result = execute(migrate_down)
        if env.previous_release:
          print green("=> Deactivating current release")
          run("ln -sfn %s releases/current" % env.previous_release)
          run("rm -rf releases/%s" % env.current_release)
        else:
          abort(red("No previous releases found."))
      else:
        if env.stages['migrated_db']:
          result=execute(migrate_down)

        if env.stages['deployed_pkg']:
          if env.stages['activated']:
            if env.previous_release:
              print green("=> switching back to previous release")
              run("ln -sfn %s releases/current" % env.previous_release)

          print green("=> removing failed deployment")
          run("rm -rf %s" % env.release_dir)

        if env.auto_mode == 'yes':
          abort(red("Rollback performed during deployment. Please check for errors."))
    else:
      abort(red("You must bootstrap your environment before rollback."))
