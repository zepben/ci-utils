packer {
  required_plugins {
    docker = {
      source  = "github.com/hashicorp/docker"
      version = "~> 1"
    }
  }
}

variable "dockerhub_pw" {
  type = string
}

variable "dockerhub_user" {
  type = string
}

source "docker" "image" {
  commit = "true"
  image  = "debian:bookworm-20240701-slim"
}

build {
  sources = ["source.docker.image"]

  provisioner "shell" {
    scripts = ["amazoncorretto-install-dependencies.sh", "../init.sh", "init.sh"]
  }

  provisioner "file" {
    destination = "/scripts"
    source      = "../scripts/"
  }

  provisioner "file" {
    destination = "/scripts"
    source      = "../scripts-build/"
  }

  provisioner "file" {
    destination = "/usr/share/maven/conf/settings.xml"
    source      = "maven-settings.xml"
  }

  provisioner "file" {
    destination = "/scripts"
    source      = "./scripts/"
  }

  provisioner "file" {
    destination = "/root/.aws/"
    source      = "../basic/aws/"
  }

  post-processors {
    post-processor "docker-tag" {
      name       = "docker.tag"
      repository = "zepben/pipeline-java"
      tags       = ["4.5.0"]
    }
    post-processor "docker-push" {
      name           = "docker.push"
      login           = true
      login_password = "${var.dockerhub_pw}"
      login_username = "${var.dockerhub_user}"
    }
  }
}
