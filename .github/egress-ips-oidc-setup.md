# OIDC setup for the egress-IPs workflow

Reference notes for provisioning the GitHub Actions OIDC trust that the
`update-egress-ips` workflow (in `Popsink/docs`) will use to read NAT
Gateway / Cloud NAT addresses. No long-lived cloud credentials — the
workflow exchanges its GitHub-issued OIDC token for short-lived credentials
on each run.

Trust is scoped to `Popsink/docs`, `ref:refs/heads/main` only — PR branches
and forks cannot assume the role / impersonate the service account.

## AWS — account `733281893834` (production)

```hcl
data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "github_actions_egress_ips_reader" {
  name = "github-actions-egress-ips-reader"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        StringLike   = { "token.actions.githubusercontent.com:sub" = "repo:Popsink/docs:ref:refs/heads/main" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "egress_ips_reader" {
  name = "describe-nat-gateways"
  role = aws_iam_role.github_actions_egress_ips_reader.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:DescribeNatGateways", "ec2:DescribeRegions"]
      Resource = "*" # Describe* calls don't support resource-level scoping
    }]
  })
}
```

Only one OIDC provider is allowed per URL per AWS account — skip
`aws_iam_openid_connect_provider` if `token.actions.githubusercontent.com`
is already registered for another workflow.

**Need back from this side:** the role ARN
(`aws_iam_role.github_actions_egress_ips_reader.arn`).

## GCP — project `popsink-production-438615`

The `popsink-production-438615.svc.id.goog` pool that already exists is
GKE's built-in Workload Identity pool — not reusable for external (GitHub)
OIDC. This needs its own dedicated pool.

```hcl
resource "google_iam_workload_identity_pool" "github_actions" {
  workload_identity_pool_id = "github-actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_actions.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == \"Popsink/docs\" && assertion.ref == \"refs/heads/main\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "github_actions_egress_ips_reader" {
  account_id   = "github-actions-egress-ips"
  display_name = "GitHub Actions - egress IPs reader"
}

resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = google_service_account.github_actions_egress_ips_reader.name
  role                = "roles/iam.workloadIdentityUser"
  member              = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions.name}/attribute.repository/Popsink/docs"
}

resource "google_project_iam_custom_role" "egress_ips_reader" {
  role_id     = "egressIpsReader"
  title       = "Egress IPs reader"
  permissions = ["compute.addresses.list", "compute.addresses.get", "compute.regions.list"]
}

resource "google_project_iam_member" "egress_ips_reader_binding" {
  project = "popsink-production-438615"
  role    = google_project_iam_custom_role.egress_ips_reader.id
  member  = "serviceAccount:${google_service_account.github_actions_egress_ips_reader.email}"
}
```

**Need back from this side:**
- the Workload Identity Provider resource name
  (`projects/<number>/locations/global/workloadIdentityPools/github-actions/providers/github`)
- the service account email
  (`github-actions-egress-ips@popsink-production-438615.iam.gserviceaccount.com`)

## Wiring into the workflow

Once applied, the workflow's auth steps will look like:

```yaml
permissions:
  id-token: write   # required for both OIDC exchanges
  contents: write    # to open the PR
  pull-requests: write

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::733281893834:role/github-actions-egress-ips-reader
      aws-region: us-east-1

  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: projects/<number>/locations/global/workloadIdentityPools/github-actions/providers/github
      service_account: github-actions-egress-ips@popsink-production-438615.iam.gserviceaccount.com
```

Send me the three values above once applied and I'll fill them into the
workflow.
