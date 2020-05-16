import base64
import boto3
import docker
import logging
import requests
import time
import yaml

#logging = logging.getLogger(__name__)
#myFormatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
logging.basicConfig(format='[%(asctime)s] [%(levelname)s] %(message)s', level=logging.INFO)

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

'''
client = docker.DockerClient(base_url='unix://run/docker.sock')
containers = client.containers.list()
for container in containers:
    print(f"{container.id}\t{container.name}")
'''

def aws_region_id():
    response = requests.get(AWS_REGION_ID)
    return response.text[:-1]

def aws_instance_id():
    response = requests.get(AWS_INSTANCE_ID)
    return response.text

def aws_get_authorization_token(repositoryId):
    response = aws_ecr_client.get_authorization_token(registryIds=[repositoryId])
    return response['authorizationData'][0]['authorizationToken']

def _get_username_password_from_token(token):
    return base64.b64decode(token).decode("utf-8").split(':')

def docker_login(username, password, registry):
    return docker_client.login(username=username, password=password, registry=registry)

def docker_containers(all=False):
    return docker_client.containers.list(all=all, filters={"name": DOCKER_DEFAULT_NAME})

def docker_find_images(repository):
    return docker_client.images.list(name=repository)

def docker_pull_image(repositoryUri):
    if not docker_client.images.pull(repositoryUri):
        logging.error(f"[ERROR] Coud not pull: {repositoryUri}")
        return False
    return True

def docker_start_container(image, user_config):
    docker_stop_containers()
    mandatory_config = {"auto_remove": True, "detach": True, "name": DOCKER_DEFAULT_NAME}
    config = {**user_config, **mandatory_config}
    return docker_client.containers.run(image, **config)

def docker_stop_containers():
    logging.info("Stopping containers...")
    containers = docker_containers()
    for container in containers:
        logging.info(f"  {container.name}")
        container.stop()
        container.wait()
    logging.info("Waiting for containers to finish")
    # The wait() above should block, but didn't. Putting in manual sleep until debug
    time.sleep(10)
    while len(docker_containers()) > 0:
        logging.info("...")
        time.sleep(10)
    

def finish():
    logging.info("Done. Sleeps...zzz")
    logging.info("--------------------------------------")
    time.sleep(10)

def deploy(instance_id):
    payload = {"id": instance_id}
    repository_details = requests.get("https://deploy.davao.io/api/deploy/instance", params=payload)
    overlord = repository_details.json()
    logging.debug(overlord)
    if len(overlord['details']) != 1:
        logging.error(f"[ERROR] Didn't receive one repository detail. Instance: {instance_id}")
        logging.error(overlord)
    full_uri = f"{overlord['details'][0]['repositoryUri']}:{overlord['deployed']['image_tag']}"
    image_tag = f"{overlord['details'][0]['repositoryUri']}:{overlord['deployed']['image_tag']}"
    logging.info(f"[OVERLORD] Currently Deployed: {image_tag}")
    #print(f"Looking for: {overlord['details'][0]['repositoryUri']}")
    images = docker_find_images(overlord['details'][0]['repositoryUri'])
    #print(images)
    #images = docker_find_images('overlord')
    aws_token = aws_get_authorization_token(overlord['details'][0]['registryId'])
    #print(aws_token)
    username, password = _get_username_password_from_token(aws_token)
    #print(password)
    if docker_login(username, password, overlord['details'][0]['repositoryUri'].split('/')[0]):
        logging.debug("Logged in!")
    if len(images) == 0:
        logging.info(f"[INFO] Fresh install. No previous instance of: {overlord['details'][0]['repositoryUri']}")
        docker_pull_image(full_uri)
    else:
        found = False
        for image in images:
            logging.debug(f"looking for: {image_tag}")
            for tag in image.tags:
                logging.debug(f"In: {tag}")
            if image_tag in image.tags:
                found = True
        if found:
            logging.info("Image exists!")
        if not found:        
            logging.info(f"Image not found: {image_tag}")
            docker_pull_image(full_uri)
    containers = docker_containers()
    # There should only be one container named "app", but let's use a loop for now,
    #  and handle errors later when the solution is better defined
    currently_running = False
    for container in containers:
        for images in container.image.tags:
            if image_tag in images:
                currently_running = True
    
    if currently_running:
        logging.info("The current app is already running")
    else:
        logging.info("it's not running. Let's start it!")
        config = yaml.load(overlord['deployed']['config'], Loader=Loader)
        logging.info(f"Using Config: {config}")
        docker_start_container(image_tag, config)
    
def main():
    #instance_id = aws_instance_id()
    instance_id = 'i-071096d81d569fa6d'
    logging.info(f"Instance ID: {instance_id}")
    while True:
        deploy(instance_id)
        finish()


# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html

AWS_INSTANCE_ID="http://169.254.169.254/latest/meta-data/instance-id"
DOCKER_DEFAULT_NAME="app1"
#AWS_REGION_ID="http://169.254.169.254/latest/meta-data/placement/availability-zone"
aws_ecr_client = boto3.client('ecr', region_name='ap-southeast-1')
docker_client = docker.DockerClient(base_url='unix://run/docker.sock')


if __name__ == "__main__":
    main()
