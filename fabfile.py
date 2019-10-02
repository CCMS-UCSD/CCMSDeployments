from fabric2 import Connection
from fabric2 import task
from fabric2 import config
import os
import time
from xml.etree import ElementTree as ET
import uuid
import glob
import json
import urllib.parse

workflow_components = ['input.xml', 'binding.xml', 'flow.xml', 'result.xml', 'tool.xml']

def read_makefile(workflow_name):
    params = {}
    makefile_location = os.path.join(workflow_name,'Makefile')
    with open(makefile_location) as f:
        for l in f:
            split_line = l.rstrip().split('=')
            if len(split_line) == 2:
                params[split_line[0]] = split_line[1]
    params['LAST_UPDATED'] = time.ctime(os.path.getmtime(makefile_location))
    return params

@task
def update_workflow_from_makefile(c, workflow_name, subcomponents):
    params = read_makefile(workflow_name)
    update_all(c, params["WORKFLOW_VERSION"], params.get("WORKFLOW_NAME"), params.get("TOOL_FOLDER_NAME"), workflow_name, subcomponents=subcomponents)

@task
def update_all(c, workflow_version, workflow_name=None, tool_name=None, base_dir=".", subcomponents=None, force_update_string='yes'):
    if workflow_version == None:
        exit("A workflow cannot be deployed without a version.")
    if workflow_name:
        update_workflow_xml(c, workflow_name, tool_name, workflow_version, base_dir=base_dir, subcomponents=subcomponents, force_update_string=force_update_string)
    if tool_name:
        update_tools(c, tool_name, workflow_version, base_dir)

    if force_update_string != 'yes':
        server_url_base = "https://proteomics2.ucsd.edu/ProteoSAFe/index.jsp?params="
        workflow_url = server_url_base + urllib.parse.quote(json.dumps({"workflow":workflow_name, "workflow_version":workflow_version}))
        print("SUCCESS:\n\n{} updated at:\n\n{}\n\n".format(workflow_name, workflow_url))

@task
def read_workflows_from_yml(c):
    workflows_to_deploy = []
    if "workflows" not in c:
        exit("Deploy all only works if a list of workflows to deploy is specified.")
    for workflow in c["workflows"]:
        workflow_name = None
        subcomponents = workflow_components
        if isinstance(workflow,dict):
            for workflow, xml in workflow.items():
                workflow_name = workflow
                subcomponents = xml
        else:
            workflow_name = workflow
        workflows_to_deploy.append((workflow_name, subcomponents))
    return workflows_to_deploy

def read_all_tools(base_dir = '.'):
    all_tools = {}
    all_submodules = glob.glob(os.path.join(base_dir, '*'))
    for submodule in all_submodules:
        if 'CCMSDeployments' not in submodule and os.path.isdir(submodule):
            submodule_params = read_makefile(submodule)
            tool_name = submodule_params.get("TOOL_FOLDER_NAME")
            workflow_name = submodule_params.get("WORKFLOW_NAME")
            if workflow_name:
                workflow_name = os.path.join(submodule.split('/')[1], workflow_name)
            version = submodule_params["WORKFLOW_VERSION"]
            if tool_name:
                all_tools[tool_name] = (version, workflow_name)
    return all_tools

@task
def deploy_all(c):
    for workflow, subcomponents in read_workflows_from_yml(c):
        update_workflow_from_makefile(c, workflow, subcomponents)

@task
def read_dependencies(c, workflow_name, rewrite_string = 'no', base_dir = '.'):
    tools = read_all_tools('..')
    rewrite = rewrite_string == 'yes'
    print('')
    changes = output_updates(c, workflow_name, tool_name = None, base_dir = base_dir, tools = tools, seen = {}, rewrite = False)
    print('')
    if changes and rewrite:
        output_updates(c, workflow_name, tool_name = None, base_dir = base_dir, tools = tools, seen = {}, rewrite = True)

def output_updates(c, workflow_name = None, tool_name = None, base_dir = '.', tools = None, seen = {}, rewrite = False):
    changes = False
    if workflow_name:
        dependencies = output_tool_dependencies(workflow_name, base_dir)
        outputs = []
        for (dependency, version) in dependencies:
            status = "N/V"
            if dependency in tools and dependency not in seen:
                new_version = False
                local_version, workflow = tools[dependency]
                seen[dependency] = (new_version,local_version)
                if version == local_version:
                    status = "{}".format(version)
                else:
                    status = "{}->{}".format(version, local_version)
                    new_version = True
                if workflow:
                    seen = output_updates(c, workflow, dependency, '..', tools, seen, rewrite)
                outputs.append("\t{} {}".format(dependency, status))
            elif dependency not in seen:
                seen[dependency] = (None,None)
                outputs.append("\tUntracked: {}".format(dependency))
        print(workflow_name.split('/')[0])
        for output in outputs:
            print(output)
        if rewrite:
            changes = rewrite_tool_w_new_dependencies(workflow_name, seen, base_dir = base_dir)
        print('')
    return seen

def output_tool_dependencies(workflow_name, base_dir = '.'):
    dependencies = []
    local = os.path.join(base_dir, workflow_name, 'tool.xml')
    tree = ET.parse(local)
    root = tree.getroot()
    for path in root.findall('pathSet'):
        if not '$base' in path.attrib['base']:
            split_full_path = path.attrib['base'].split('/')
            tool_name = split_full_path[0]
            if len(split_full_path) >= 2:
                tool_version = split_full_path[1]
            else:
                tool_version = "NV"
            dependencies.append((tool_name, tool_version))
    return dependencies

def rewrite_tool_w_new_dependencies(workflow_name, updates, rewrite = False, base_dir = '.'):
    changes_made = False
    dependencies = []
    local = os.path.join(base_dir, workflow_name, 'tool.xml')
    tree = ET.parse(local)
    root = tree.getroot()
    for path in root.findall('pathSet'):
        if not '$base' in path.attrib['base']:
            split_full_path = path.attrib['base'].split('/')
            tool_name = split_full_path[0]
            if tool_name in updates and updates[tool_name][1]:
                changes_made = True
                if len(split_full_path[2:]) == 0:
                    path.attrib['base'] = os.path.join(tool_name, updates[tool_name][1])
                else:
                    path.attrib['base'] = os.path.join(tool_name, updates[tool_name][1], '/'.join(split_full_path[2:]))
    if changes_made:
        tree.write(local)
    return changes_made

@task
def generate_manifest(c):
    for workflow, subcomponents in read_workflows_from_yml(c):
        params = read_makefile(workflow)
        flag = ""
        if "WORKFLOW_NAME" not in params:
            flag = " (Tool only)"
        elif "TOOL_FOLDER_NAME" not in params:
            flag = " (Workflow only)"
        print('{}{}, version: {}, last updated: {}'.format(workflow,flag,params['WORKFLOW_VERSION'],params['LAST_UPDATED']))

@task
def update_workflow_xml(c, workflow_name, tool_name, workflow_version, base_dir=".", subcomponents=None, force_update_string='yes'):
    if not subcomponents:
        subcomponents = workflow_components

    force_update = force_update_string == 'yes'
    production = "production" in c

    production_user = c["production"]["workflow_user"] if production else None

    local_temp_path = os.path.join("/tmp/{}_{}_{}".format(workflow_name, workflow_version, str(uuid.uuid4())))
    c.local("mkdir -p {}".format(local_temp_path))

    for component in subcomponents:
        rewrite_workflow_component(component, base_dir, workflow_name, tool_name, workflow_version, local_temp_path)

    base_workflow_path = os.path.join(c["paths"]["workflows"], workflow_name, "versions")
    versioned_workflow_path = os.path.join(c["paths"]["workflows"], workflow_name, "versions", workflow_version)

    if production_user:
        c.sudo("mkdir -p {}".format(base_workflow_path), user=production_user, pty=True)
        c.sudo("mkdir -p {}".format(versioned_workflow_path), user=production_user, pty=True)
    else:
        c.run("mkdir -p {}".format(base_workflow_path))
        c.run("mkdir -p {}".format(versioned_workflow_path))

    for component in subcomponents:
        # print(component)
        if force_update:
            update_workflow_component(c, local_temp_path, workflow_name, component, production_user=production_user) #Adding to active default version
        update_workflow_component(c, local_temp_path, workflow_name, component, workflow_version=workflow_version, production_user=production_user) #Explicitly adding versioned

#Uploading the actual tools to the server
@task
def update_tools(c, workflow_name, workflow_version, base_dir="."):
    production = "production" in c
    production_user = c["production"]["tool_user"] if production else None

    final_path = os.path.join(c["paths"]["tools"],workflow_name, workflow_version)

    if production_user:
        c.sudo("mkdir -p {}".format(final_path), user=production_user, pty=True)
    else:
        c.run("mkdir -p {}".format(final_path))

    local_path = os.path.join(base_dir, 'tools', workflow_name)

    update_folder(c, local_path, final_path, production_user=production_user)


#Utility Functions

def rewrite_workflow_component(component, base_dir, workflow_name, tool_name, workflow_version, local_temp_path):
    local = os.path.join(base_dir, workflow_name, component)
    temp = os.path.join(local_temp_path,component)
    tree = ET.parse(local)
    root = tree.getroot()
    if component in ['input.xml','result.xml']:
        root.set('id', workflow_name)
        root.set('version', workflow_version)
    elif component in ['flow.xml']:
        root.set('name', workflow_name)
    elif component in ['tool.xml']:
        for path in root.findall('pathSet'):
            if '$base' in path.attrib['base']:
                if tool_name:
                    path.attrib['base'] = path.attrib['base'].replace('$base',os.path.join(tool_name,workflow_version))
                else:
                    exit("Cannot rewrite tool.xml without specifying tool name.")
    tree.write(temp)

#TODO: Validate that the xml is also a valid workflow
def update_workflow_component(c, local_temp_path, workflow_filename, component, workflow_version=None, production_user=None):
    local = os.path.join(local_temp_path,component)

    if workflow_version:
        server = os.path.join(c["paths"]["workflows"], workflow_filename, "versions", workflow_version, component)
    else:
        server = os.path.join(c["paths"]["workflows"], workflow_filename, component)

    update_file(c, local, server, production_user=production_user)



#Update File
def update_file(c, local_path, final_path, production_user = None):
    if production_user:
        remote_temp_path = os.path.join("/tmp/{}_{}".format(local_path.replace("/", "_"), str(uuid.uuid4())))
        c.put(local_path, remote_temp_path, preserve_mode=True)
        c.sudo('cp {} {}'.format(remote_temp_path, final_path), user=production_user, pty=True)
    else:
        c.put(local_path, final_path, preserve_mode=True)

#TODO: update this to work with rsync
def update_folder(c, local_path, final_path, production_user = None):
    #Tar up local folder and upload to temporary space on server and untar
    local_temp_path = os.path.join("/tmp/{}_{}.tar".format(local_path.replace("/", "_"), str(uuid.uuid4())))
    cmd = "tar -C {} -chf {} .".format(local_path, local_temp_path)
    # print(cmd)
    os.system(cmd)

    remote_temp_tar_path = os.path.join("/tmp/{}_{}.tar".format(local_path.replace("/", "_"), str(uuid.uuid4())))
    c.put(local_temp_path, remote_temp_tar_path, preserve_mode=True)

    remote_temp_path = os.path.join("/tmp/{}_{}".format(local_path.replace("/", "_"), str(uuid.uuid4())))
    c.run("mkdir {}".format(remote_temp_path))
    c.run("tar -C {} -xf {}".format(remote_temp_path, remote_temp_tar_path))

    if production_user:
        c.sudo('rsync -rlptD {}/ {}'.format(remote_temp_path, final_path), user=production_user, pty=True)
    else:
        c.run('rsync -rlptD {}/ {}'.format(remote_temp_path, final_path))
