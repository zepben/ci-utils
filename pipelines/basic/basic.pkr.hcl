packer {
  required_plugins {
    docker = {
      source  = "github.com/hashicorp/docker"
      version = "~> 1"
    }
  }
}

variable "dockerhub_pw" {
  type    = string
  default = "${env("DOCKER_HUB_ACCESS_TOKEN")}"
}

variable "dockerhub_user" {
  type    = string
  default = "${env("DOCKER_HUB_USER")}"
}

variable "container_version_tag" {
  type = string
  default = "5.7.3"
}

source "docker" "image" {
  commit = "true"
  image  = "alpine"
}

build {
  sources = ["source.docker.image"]

  provisioner "file" {
    destination = "/scripts"
    source      = "./scripts/"
  }

  provisioner "shell" {
    scripts = ["install-dependencies.sh", "../init.sh"]
  }

  provisioner "file" {
    destination = "/scripts"
    source      = "../scripts/"
  }

  provisioner "file" {
    destination = "/scripts"
    source      = "../CSharp/scripts/"
  }

  provisioner "file" {
    destination = "/scripts"
    source      = "../Java/scripts/"
  }

  provisioner "file" {
    destination = "/scripts"
    source      = "../JavaScript/scripts/"
  }

  provisioner "file" {
    destination = "/scripts"
    source      = "../Python/scripts/"
  }

  provisioner "file" {
    destination = "/root/.aws/"
    source      = "./aws/"
  }

  post-processors {
    post-processor "docker-tag" {
      repository = "zepben/pipeline-basic"
      tags       = [var.container_version_tag]
    }
    post-processor "docker-push" {
      login          = true
      login_password = "${var.dockerhub_pw}"
      login_username = "${var.dockerhub_user}"
    }
  }
}
