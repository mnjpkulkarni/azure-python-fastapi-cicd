import os
import shutil
import subprocess


def find_executable(name: str):
    path = shutil.which(name) or shutil.which(f"{name}.cmd")
    if not path:
        raise FileNotFoundError(f"Executable not found: {name}")
    return path


class AzureCLIAuth:
    @staticmethod
    def ensure_authenticated():
        az_cmd = find_executable("az")

        client_id = os.getenv("AZURE_CLIENT_ID")
        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")
        use_identity = os.getenv("AZURE_USE_MANAGED_IDENTITY", "false").lower() in ("1", "true", "yes")

        if client_id and tenant_id and client_secret:
            print("Authenticating Azure CLI using service principal")
            CommandExecutor.run([
                az_cmd,
                "login",
                "--service-principal",
                "-u",
                client_id,
                "-p",
                client_secret,
                "--tenant",
                tenant_id,
            ])
            return

        if use_identity:
            print("Authenticating Azure CLI using managed identity")
            CommandExecutor.run([az_cmd, "login", "--identity"])
            return

        print("Checking existing Azure CLI authentication")
        CommandExecutor.run([az_cmd, "account", "show"])


# -----------------------------
# Base command executor
# -----------------------------
class CommandExecutor:
    @staticmethod
    def run(command: list, cwd: str = None):
        print(f"Executing: {' '.join(command)}")

        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True
            )

            if result.stdout:
                print(result.stdout)

            return result.stdout

        except subprocess.CalledProcessError as e:
            print("ERROR:", e.stderr)
            raise


# -----------------------------
# Step 1: Repo management
# -----------------------------
class RepoManager:
    def __init__(self, repo_url: str, branch: str, target_dir: str):
        self.repo_url = repo_url
        self.branch = branch
        self.target_dir = target_dir
        self.pat = os.getenv("ADO_PAT")

    def _authenticated_repo_url(self):
        if self.pat and "dev.azure.com" in self.repo_url and "@" not in self.repo_url:
            scheme, rest = self.repo_url.split("://", 1)
            return f"{scheme}://{self.pat}@{rest}"
        return self.repo_url

    def checkout(self):
        repo_url = self._authenticated_repo_url()

        if os.path.exists(self.target_dir):
            print("Repo exists → pulling latest changes")

            CommandExecutor.run(
                ["git", "-C", self.target_dir, "pull"]
            )
        else:
            print("Cloning repository")

            CommandExecutor.run([
                "git",
                "clone",
                "-b",
                self.branch,
                repo_url,
                self.target_dir
            ])


# -----------------------------
# Step 2: Docker build & push
# -----------------------------
# class DockerManager:
#     def __init__(self, image_name: str, tag: str, acr_name: str):
#         self.image_name = image_name
#         self.tag = tag
#         self.acr_name = acr_name

#         self.full_image = f"{acr_name}.azurecr.io/{image_name}:{tag}"

#     def build(self, context_path: str):
#         print("Building Docker image")

#         CommandExecutor.run([
#             "docker",
#             "build",
#             "-t",
#             self.full_image,
#             context_path
#         ])

#     def push(self):
#         print("Logging into Azure Container Registry")

#         CommandExecutor.run([
#             "az",
#             "acr",
#             "login",
#             "--name",
#             self.acr_name
#         ])

#         print("Pushing image to ACR")

#         CommandExecutor.run([
#             "docker",
#             "push",
#             self.full_image
#         ])

class ACRCIManager:

    def __init__(self, registry: str, image_name: str, tag: str = "latest"):
        self.registry = registry
        self.image_name = image_name
        self.tag = tag

    def build(self, context_path: str = "./repo"):
        image_full = f"{self.registry}.azurecr.io/{self.image_name}:{self.tag}"

        print(f"Triggering ACR build for {image_full}")
        print(f"Context path: {context_path}")

        if not os.path.exists(context_path):
            raise FileNotFoundError(f"Build context not found: {context_path}")

        AzureCLIAuth.ensure_authenticated()
        az_cmd = find_executable("az")

        # Set UTF-8 encoding for Windows compatibility
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["NO_COLOR"] = "1"

        result = subprocess.run([
            az_cmd,
            "acr",
            "build",
            "--registry",
            self.registry,
            "--image",
            image_full,
            "--no-logs",
            context_path,
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            print(f"ACR build failed with return code {result.returncode}")
            print(f"Error output:\n{error_msg}")
            raise Exception(f"ACR build failed: {error_msg}")

        print(result.stdout)
        return image_full


# -----------------------------
# Step 3: Azure deployment
# -----------------------------
class AzureDeployer:
    def __init__(self, app_name: str, resource_group: str, image: str):
        self.app_name = app_name
        self.resource_group = resource_group
        self.image = image

    def deploy(self):
        print("Deploying to Azure Container Apps")

        AzureCLIAuth.ensure_authenticated()
        az_cmd = find_executable("az")

        CommandExecutor.run([
            az_cmd,
            "containerapp",
            "update",
            "--name",
            self.app_name,
            "--resource-group",
            self.resource_group,
            "--image",
            self.image,
        ])


# -----------------------------
# CI/CD Orchestrator
# -----------------------------
class CICDPipeline:
    def __init__(self, repo: RepoManager, acrci: ACRCIManager, deployer: AzureDeployer):
        self.repo = repo
        self.acrci = acrci
        self.deployer = deployer

    def run(self):
        print("\n===== CI/CD PIPELINE STARTED =====\n")

        # Step 1: Checkout repo
        print("[STEP 1] Repo checkout")
        self.repo.checkout()

        # Step 2: Build Docker image
        print("\n[STEP 2] Docker build & push")
        image = self.acrci.build(self.repo.target_dir)
        
        # Update deployer with the built image
        self.deployer.image = image

        # Step 3: Deploy
        print("\n[STEP 3] Deploy to Azure")
        self.deployer.deploy()

        print("\n===== PIPELINE SUCCESS =====\n")