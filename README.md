# CCMS Deployments

These are the utility scripts/make files to get a deployment working for CCMS workflows in ProteoSAFe

## Necessary Steps To Get Working

1. Create a new repository to hold your workflows (e.g. GNPS_Workflows or Proteomics_Workflows).
1. Import CCMSDeployments as a submodule (git submodule add https://github.com/CCMS-UCSD/CCMSDeployments.git)
1. Link the following files into the root folder: fabfile.py, Makefile.deploytemplate and create yml files similar to the following for each server (or just copy from fabric-production-gnps.yml, fabric-production-proteomics.yml, fabric.yml as examples)

 ```
debug: true    # leave this alone

run:           # leave this alone
  warn: true 
  echo: true 
  
production:    # only add this section if you intend to deploy with sudo
  tool_user: gamma 
  workflow_user: ccms
  user: ccms
  
workflows:     # workflows to be deployed
  - fast_test_workflow
  
paths:         # paths for tools and workflows on the server to be deployed to
  tools: /data/cluster/tools
  workflows: /ccms/workflows
 ```

1. Create a Makefile.credentials with the USERNAME key for your username credentials on the particular server in the root folder (do not check this in)

## To Deploy a Single Test Workflow

Navigate to the `fast_test_workflow` directory and execute one of the following:

  1. ```make deploy-debug``` to deploy to proteomics2
  1. ```make deploy-debug-update``` to deploy to proteomics2 and update the default
  2. ```make deploy-production-gnps``` to deploy to gnps and update the default
  2. ```make deploy-production-gnps-pre``` to deploy to gnps
  3. ```make deploy-production-proteomics``` to deploy to proteomics and update the default
  3. ```make deploy-production-proteomics-pre``` to deploy to proteomics
  
## To Deploy All Test Workflows

For proteomics2 (using the default configuration), execute:

```fab2 -H <username>@proteomics2.ucsd.edu --prompt-for-login-password deploy-all```.

For production servers {proteomics,gnps}, execute:

```fab2 -H <username>@<server>.ucsd.edu --prompt-for-login-password --prompt-for-sudo-password deploy-all --config fabric-production-<server>.yml```

## Testing Workflows