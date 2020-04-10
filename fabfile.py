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
import io

workflow_components = ['input.xml', 'binding.xml', 'flow.xml', 'result.xml', 'tool.xml']

@task
def read_branch(c, workflow_name):
    branch_name = None
    with io.StringIO() as f:
        c.local('cd {} && git branch | grep \*'.format(workflow_name), out_stream = f)
        branch = f.getvalue().replace('\n','').replace('* ','')
        if not ('HEAD detached' in branch or 'master' in branch):
            branch_name = branch
    return branch_name

def read_makefile(workflow_name):
    params = {}
    makefile_location = os.path.join(workflow_name,'Makefile')
    with open(makefile_location) as f:
        for l in f:
            split_line = l.rstrip().split('=')
            if len(split_line) >= 2:
                params[split_line[0]] = '='.join(split_line[1:])
    params['LAST_UPDATED'] = time.ctime(os.path.getmtime(makefile_location))
    return params

@task
def update_workflow_from_makefile(c, workflow_name, subcomponents):
    params = read_makefile(workflow_name)
    update_all(c, params["WORKFLOW_VERSION"], params.get("WORKFLOW_NAME"), params.get("TOOL_FOLDER_NAME"), params.get("WORKLFLOW_LABEL"), params.get("WORKLFLOW_DESCRIPTION"), workflow_name, subcomponents=subcomponents)

@task
def update_all(c, workflow_version, workflow_name=None, tool_name=None, workflow_label=None, workflow_description=None, base_dir=".", subcomponents=None, force_update_string='yes'):
    production = "production" in c

    if workflow_version == None:
        exit("A workflow cannot be deployed without a version.")

    branch_name = read_branch(c, base_dir)
    if branch_name and not production:
        workflow_version = '{}+{}'.format(workflow_version, branch_name.replace(' ','_'))

    if workflow_name:
        update_workflow_xml(c, workflow_name, tool_name, workflow_version, workflow_label, workflow_description, base_dir=base_dir, subcomponents=subcomponents, force_update_string=force_update_string)
    if tool_name:
        update_tools(c, tool_name, workflow_version, base_dir)

    server_url_base = "https://{}/ProteoSAFe/index.jsp?params=".format(c.host)
    workflow_url = server_url_base + urllib.parse.quote(json.dumps({"workflow":workflow_name.upper(), "workflow_version":workflow_version}))
    print("SUCCESS:\n\n{} updated at with version:\n\n{}\n\n".format(workflow_name, workflow_url))

    if force_update_string == 'yes':
        server_url_base = "https://{}/ProteoSAFe/index.jsp?params=".format(c.host)
        workflow_url = server_url_base + urllib.parse.quote(json.dumps({"workflow":workflow_name.upper()}))
        print("And default version :\n\n{}\n\n".format(workflow_url))

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
            try:
                submodule_params = read_makefile(submodule)
                tool_name = submodule_params.get("TOOL_FOLDER_NAME")
                version = submodule_params["WORKFLOW_VERSION"]
                if tool_name:
                    all_tools[tool_name] = (version, submodule)
            except:
                pass
    return all_tools

@task
def deploy_all(c):
    for workflow, subcomponents in read_workflows_from_yml(c):
        update_workflow_from_makefile(c, workflow, subcomponents)

@task
def read_dependencies(c, workflow_name, rewrite_string = 'no', base_dir = '.'):
    tools = read_all_tools('..')
    rewrite = rewrite_string == 'yes'
    output_updates(c, workflow_name, tool_name = None, base_dir = base_dir, tools = tools, seen = {}, rewrite = rewrite)
    print('')

@task
def is_on_server(c, tool_name, tool_version):
    tool_path = os.path.join(c["paths"]["tools"],tool_name, tool_version)

    production = "production" in c
    production_user = c["production"]["workflow_user"] if production else None

    on_server = False

    if production_user:
        on_server = c.sudo("test -e {}".format(tool_path), user=production_user, pty=True)
    else:
        on_server = c.run("test -e {}".format(tool_path))

    return not on_server.return_code


def output_updates(c, workflow_name = None, tool_name = None, base_dir = '.', tools = None, seen = {}, rewrite = False):
    updates = {}
    if workflow_name:
        dependencies = output_tool_dependencies(workflow_name, base_dir)
        outputs = []

        for (dependency, version) in dependencies:

            status = "N/V"
            if dependency not in seen or (dependency in seen and seen[dependency] != version):
                update = False
                deployed = False
                if dependency in tools:

                    local_version, workflow = tools[dependency]

                    if version == local_version:
                        status = "{}".format(version)
                    else:
                        update = True
                        updates[dependency] = local_version
                        status = "{}->{}".format(version, local_version)

                    if version and is_on_server(c, dependency, local_version):
                        deployed = True

                    deployed_str = " (deployed)" if deployed else " (needs deployment)"

                    # if rewrite:
                    #     if not deployed:
                    #         update_workflow_from_makefile(c, workflow, workflow_components, True)
                    #         status += " (updated)"
                    #     else:
                    #         status += " (already deployed)"
                    # else:
                    #     status += deployed_str

                    status += deployed_str

                    outputs.append((update or deployed,"\t{} {}".format(dependency, status)))
                else:
                    outputs.append((update or deployed,"\t{} untracked".format(dependency)))

            seen[dependency] = version

        if not rewrite:
            print('\nDepenencies for {}:'.format(workflow_name))
            for output in outputs:
                print(output[1])
        else:
            print('\nUpdated depenencies for {}:'.format(workflow_name))
            for output in outputs:
                if output[0]:
                    print(output[1])
            rewrite_tool_w_new_dependencies(workflow_name, updates, base_dir = base_dir)

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
                tool_name = '/'.join(split_full_path[0:-1])
                tool_version = split_full_path[-1]
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
        if not '$base' in path.get('base'):
            split_full_path = path.get('base').split('/')
            tool_name = split_full_path[0]
            if tool_name in updates and updates[tool_name]:
                changes_made = True
                if len(split_full_path[2:]) == 0:
                    path.set('base',os.path.join(tool_name, updates[tool_name]))
                else:
                    path.set('base',os.path.join(tool_name, updates[tool_name], '/'.join(split_full_path[2:])))
    if changes_made:
        tree.write(local)

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
def update_workflow_xml(c, workflow_name, tool_name, workflow_version, workflow_label, workflow_description, base_dir=".", subcomponents=None, force_update_string='yes'):
    if not subcomponents:
        subcomponents = workflow_components

    force_update = force_update_string == 'yes'
    production = "production" in c

    production_user = c["production"]["workflow_user"] if production else None

    local_temp_path = os.path.join("/tmp/{}_{}_{}".format(workflow_name, workflow_version, str(uuid.uuid4())))
    c.local("mkdir -p {}".format(local_temp_path))

    for component in subcomponents:
        rewrite_workflow_component(component, base_dir, workflow_name, tool_name, workflow_version, workflow_label, workflow_description, local_temp_path)

    #Performing Workflow Files Validation
    try:
        validate_workflow_xml(local_temp_path)
    except:
        print("Validation Failed in Exception")

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

    if not production_user:
        c.run("chmod -R 777 {}".format(os.path.join(c["paths"]["workflows"], workflow_name)))


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

    if not production_user:
        c.run("chmod -R 777 {}".format(os.path.join(c["paths"]["tools"],workflow_name)))


#Utility Functions

def rewrite_workflow_component(component, base_dir, workflow_name, tool_name, workflow_version, workflow_label, workflow_description, local_temp_path):
    local = os.path.join(base_dir, workflow_name, component)
    temp = os.path.join(local_temp_path,component)
    tree = ET.parse(local)
    root = tree.getroot()
    if component in ['input.xml','result.xml']:
        root.set('id', workflow_name)
        root.set('version', workflow_version)
        if component in ['input.xml']:
            for path in root.findall('workflow-id'):
                path.text = workflow_name.upper()
            for path in root.findall('workflow-label'):
                if workflow_label:
                    path.text = workflow_label
            if workflow_description is not None:
                description_block = ET.Element("block")
                root.insert(0, description_block)
                description_block.attrib["label"] = "Workflow Description"
                description_row = ET.SubElement(description_block, "row")
                description_cell = ET.SubElement(description_row, "cell")
                description_label = ET.SubElement(description_cell, "label")
                description_label.attrib["prefix"] = "false"
                description_content = ET.SubElement(description_label, "content")
                description_content.text = '<div style="5px;padding:1px; border:2px;margin-left:8%;margin-right:8%;text-align:left">\
                    <br><strong>{}</strong> \
                    <hr style="margin-top:5px;margin-bottom:5px"> \
                    {} \
                    <hr style="margin-top:5px;margin-bottom:5px"> \
                    <small>Workflow version {} </small> \
                    </div>'.format(workflow_label if workflow_label else workflow_name.upper(), workflow_description, workflow_version)

    elif component in ['flow.xml']:
        root.set('name', workflow_name)
    elif component in ['tool.xml']:
        for path in root.findall('pathSet'):
            if '$base' in path.get('base'):
                if tool_name:
                    path.set('base',path.get('base').replace('$base',os.path.join(tool_name,workflow_version)))
                else:
                    exit("Cannot rewrite tool.xml without specifying tool name.")
    tree.write(temp)

def validate_workflow_xml(local_temp_path):
    import workflow_validator

    flow_path = os.path.join(local_temp_path, "flow.xml")
    binding_path = os.path.join(local_temp_path, "binding.xml")
    tool_path = os.path.join(local_temp_path, "tool.xml")

    workflow_obj = workflow_validator.Workflow(flow_path, binding_path, tool_path)
    workflow_obj.validate()

    print(workflow_obj.printerrors())


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
        if os.path.split(os.path.normpath(remote_temp_path))[0] == '/tmp':
            c.run('rm {}'.format(remote_temp_path))
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

    if os.path.split(os.path.normpath(remote_temp_path))[0] == '/tmp':
        c.run('rm -rf {}'.format(remote_temp_path))
    if os.path.split(os.path.normpath(remote_temp_tar_path))[0] == '/tmp':
        c.run('rm {}'.format(remote_temp_tar_path))
