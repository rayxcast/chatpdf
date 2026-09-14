# Security policy

ChatPDF is a local portfolio and learning project, not a production service. The default Docker Compose stack has no authentication, authorization, tenant isolation, rate limiting, or public-ingress hardening.

Please do not use it with confidential documents or expose it directly to the public internet. Keep API keys in the ignored `.env` file and never commit credentials, private documents, generated databases, or provider responses.

If you find a security issue, avoid publishing credentials or sensitive exploit details in a public issue. Contact the maintainer through the email listed in the project metadata or GitHub profile so the issue can be reviewed privately.
