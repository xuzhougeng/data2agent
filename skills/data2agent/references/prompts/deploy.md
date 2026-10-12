# Deploy to the selected destination

Use the user's existing deployment choice. Local execution, a private preview and public publication are distinct scopes; do not invent a new confirmation step for an already authorized action or infer public publication from a local-first request.

For a custom application, supply its actual dependency installation, start/status/stop or service configuration. For the legacy Go portal, `deploy_hosted.sh` is an optional helper for a compatible package. Other service runtimes can be installed and managed directly. A missing Go release must not disable an otherwise implementable HTTP/MCP service.

Verify:

- the service starts at the selected destination and a health endpoint answers;
- a representative real scientific query returns the accepted values;
- referenced data, indexes and download paths remain valid after relocation;
- startup configuration, runtime dependencies, file permissions and any required proxy settings match the delivered implementation;
- updates switch a consistent release and preserve unrelated projects/services.

Use identity-checked process management for a local service; never stop an unrelated process merely because its port matches an example. For a container, use a health command actually installed in that image and an endpoint valid for the domain (a figures/genome project need not have `obs`). A Compose syntax check is not a successful image build or running service.

If a registry proxy, remote credential, quota or external service blocks deployment, record the specific failed operation and complete unaffected packaging/local validation. Do not modify shared host configuration to fix another project's environment without authorization. Report the actual running URL, destination, control commands and unverified deployment methods.
