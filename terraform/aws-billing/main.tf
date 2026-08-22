data "aws_caller_identity" "current" {}

# Dedicated IAM user with access keys, not a role. The overlay polls every 15
# minutes unattended; SSO / `aws login` sessions expire and cannot assume a
# role overnight. This user has no console password.
resource "aws_iam_user" "billing_reader" {
  name = var.user_name
  path = "/conky/"

  tags = {
    Purpose   = "conky-linear-HUP affine billing map"
    ManagedBy = "terraform"
  }
}

resource "aws_iam_user_policy" "billing_reader" {
  name = "billing-read"
  user = aws_iam_user.billing_reader.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "CostExplorerMonthToDate"
        Effect   = "Allow"
        Action   = ["ce:GetCostAndUsage"]
        Resource = "*"
      },
      {
        # DescribeBudgets is a list call, so the resource has to be "*".
        Sid      = "ViewAccountBudgets"
        Effect   = "Allow"
        Action   = ["budgets:ViewBudget"]
        Resource = "*"
      },
      {
        Sid      = "ListBillingAlarms"
        Effect   = "Allow"
        Action   = ["cloudwatch:DescribeAlarms"]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_access_key" "billing_reader" {
  user = aws_iam_user.billing_reader.name
}
