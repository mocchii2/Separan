"""Default AWS Lambda entrypoint for a packaged Separan application."""

from .lambda_aws import create_aws_host_functions
from .lambda_runtime import create_lambda_handler


handler = create_lambda_handler(host_functions=create_aws_host_functions())
