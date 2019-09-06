# Necessary Steps To Get Working

1. Create a Makefile based upon the example_workflow. Specify the specific workflow name, tool folder, and Version
2. Create a Makefile.credentials with the USERNAME key for your username credentials on the particular server (do not check this in)

# To Deploy a Single Test Workflow

Navigate to the `fast_test_workflow` directory and execute one of the following:

  1. ```make deploy-debug``` to deploy to proteomics2
  2. ```make deploy-production-gnps``` to deploy to gnps
  3. ```make deploy-production-proteomics``` to deploy to proteomics
  
# To Deploy a All Workflows for a Server

For proteomics2, execute:

```fab2 -H <username>@proteomics2.ucsd.edu --prompt-for-login-password deploy-all```.

For production {proteomics,gnps} servers, execute:

```fab2 -H <username>@<server>.ucsd.edu --prompt-for-login-password --prompt-for-sudo-password deploy-all --config ../fabric-production-<server>.yml```
