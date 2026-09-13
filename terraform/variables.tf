variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "quotesapp"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "ssh_allowed_ips" {
  description = "CIDR blocks allowed to SSH into the instance"
  type        = list(string)
  default     = ["0.0.0.0/0"] # Change this to your IP for better security
}

variable "app_domain" {
  description = "Public domain the app is served on, fronted by Cloudflare"
  type        = string
}

variable "cloudflare_ipv4_cidrs" {
  description = "Cloudflare edge IPv4 ranges permitted to reach ports 80/443. Refresh from https://api.cloudflare.com/client/v4/ips"
  type        = list(string)
  default = [
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
  ]
}

variable "ssh_public_key" {
  description = "SSH public key for EC2 access"
  type        = string
}

variable "postgres_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "django_secret_key" {
  description = "Django secret key"
  type        = string
  sensitive   = true
}

variable "ses_smtp_username" {
  description = "AWS SES SMTP username"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ses_smtp_password" {
  description = "AWS SES SMTP password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ses_smtp_host" {
  description = "AWS SES SMTP host"
  type        = string
  default     = "email-smtp.ap-southeast-1.amazonaws.com"
}

variable "ses_smtp_port" {
  description = "AWS SES SMTP port"
  type        = number
  default     = 587
}

variable "default_from_email" {
  description = "Default FROM email address (must be verified in SES)"
  type        = string
}
