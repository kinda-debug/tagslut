from .get_token_client_credentials_request import GetTokenClientCredentialsRequest

# Rebuild models to resolve circular forward references
# This ensures Pydantic can properly validate models that reference each other
GetTokenClientCredentialsRequest.model_rebuild()
