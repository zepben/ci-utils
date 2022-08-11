#!/bin/bash

# Begin Standard 'imports'
set -e
set -o pipefail


gray="\\e[37m"
blue="\\e[36m"
red="\\e[31m"
yellow="\\e[33m"
green="\\e[32m"
reset="\\e[0m"

git config --global user.email "ci@zepben.com"
git config --global user.name "CI"

#######################################
# echoes a message in blue
# Globals:
#   None
# Arguments:
#   Message
# Returns:
#   None
#######################################
info() { echo -e "${blue}INFO: $*${reset}"; }

warn() { echo -e "${yellow}WARN: $*${reset}"; }

#######################################
# echoes a message in red
# Globals:
#   None
# Arguments:
#   Message
# Returns:
#   None
#######################################
error() { echo -e "${red}ERROR: $*${reset}"; }

#######################################
# echoes a message in grey. Only if debug mode is enabled
# Globals:
#   DEBUG
# Arguments:
#   Message
# Returns:
#   None
#######################################

debug() {
  if [[ "${DEBUG}" == "true" ]]; then
    echo -e "${gray}DEBUG: $*${reset}";
  fi
}

#######################################
# echoes a message in green
# Globals:
#   None
# Arguments:
#   Message
# Returns:
#   None
#######################################
success() { echo -e "${green}âœ” $*${reset}"; }

#######################################
# echoes a message in red and terminates the programm
# Globals:
#   None
# Arguments:
#   Message
# Returns:
#   None
#######################################
fail() { echo -e "${red}âœ– $*${reset}"; exit 1; }

## Enable debug mode.
enable_debug() {
  if [[ "${DEBUG}" == "true" ]]; then
    info "Enabling debug mode."
    set -x
  fi
}

#######################################
# echoes a message in blue
# Globals:
#   status: Exit status of the command that was executed.
#   output_file: Local path with captured output generated from the command.
# Arguments:
#   command: command to run
# Returns:
#   None
#######################################
run() {
  echo "$@"
  if [[ "$@" = "cd "* ]]; then
    "$@"
  else
    output_file="/var/tmp/pipe-$(date +%s)-$RANDOM"
    "$@" | tee "$output_file"
  fi
  status=$?
}

#######################################
# echoes a message in blue
# Globals:
#   status: Exit status of the command that was executed.
#   output_file: Local path with captured output generated from the command.
# Arguments:
#   command: command to run
# Returns:
#   None
#######################################
run_eval() {
  output_file="/var/tmp/pipe-$(date +%s)-$RANDOM"

  echo "$@"
  eval "$@" | tee "$output_file"
  status=$?
}

# End standard 'imports'

incr_version() {
    version_type=${1:?'Version type variable missing.'}
    version=${2:?'Version variable missing.'}

    info "Updating $version_type version..."

    IFS='.' read -r -a array <<< "$version"
    if [[ $version_type == "patch" ]]; then
        array[2]=$((++array[2]))
    elif [[ $version_type == "minor" ]]; then
        array[1]=$((++array[1]))
        array[2]=0
    elif [[ $version_type == "major" ]]; then
        array[0]=$((++array[0]))
        array[1]=0
        array[2]=0
    else
        fail "$version_type is invalid."
    fi

    new_version="${array[0]}.${array[1]}.${array[2]}"
    info "new version: $new_version"
}

commit_update_version() {
  branch=${1:-release}
  info "Commiting changes to $branch..."

  run git commit -m "Update version to next snapshot [skip ci]"

  if [[ $branch == "master" || $branch == "LTS"* || $branch == "main" ]]; then
    if [[ -z "$GITHUB_ACTIONS" ]]; then
      run git remote set-url origin "https://${BB_AUTH_STRING}@bitbucket.org/$BITBUCKET_REPO_FULL_NAME"
    fi
  fi
  run git push -u origin $branch
}

commit_finalize_version() {
  run git commit -m "Update versions for release [skip ci]"
  run git push -u origin release
}

tag_finalize_version() {
  version=${1:? 'Version variable is missing.'}
  run git tag "v$version"
  run git push --tags
}

check_tag_exists() {
  version=${1:? 'Version variable is missing.'}
  info "Checking remote tags if version exists..."
  run git config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
  run git fetch --tags origin
  old_tag=$(git tag -l | grep "^$version$" || true)
  tag=$(git tag -l | grep "^v$version$" || true)
  if [[ ! -z $tag || ! -z $old_tag ]]; then
      fail "Tag for this version already exists"
  fi
}

stage_file() {
  file=$1
  if [[ ! -z $file ]]; then
    info "Staging $file changes..."
    run git add $file
    if [[ $(git diff --staged --quiet $file)$? != 1 ]]; then
        warn "$file was not updated"
    fi
  fi
}

get_params() {
  if [ -z $allOptions ]; then
    fail "Need to set allOptions var."
  fi

  options=()
  while [ $# -gt 0 ]; do
    if [[ " ${allOptions[@]} " =~ " ${1} " ]]; then
      options+=( $1 )
      shift
    elif [[ $1 == '--'* ]]; then
      fail "Option $1 is invalid."
      break
    else
      break
    fi
  done
  IFS=' ' read -r -a args <<< "$@"
}

build_lang_options=( "--python" "--csharp" "--java" "--js" )

build_lang() {
    buildLang=${@:? 'Build lang option is required.'}
    if [[ " ${buildLang[@]} " =~ " --python " ]]; then
        source "$(dirname "$0")/py-common.sh"
    elif [[ " ${buildLang[@]} " =~ " --csharp " ]]; then
        source "$(dirname "$0")/cs-common.sh"
    elif [[ " ${buildLang[@]} " =~ " --java " ]]; then
        source "$(dirname "$0")/java-common.sh"
    elif [[ " ${buildLang[@]} " =~ " --js " ]]; then
      source "$(dirname "$0")/js-common.sh"
    else
        fail "Available build langs are ${build_lang_options[@]}."
    fi
}

java_build_tool_options=( "--maven" "--gradle" )

update_project_options=( "--no-commit" "--snapshot" "--release" "--grow-changelog" "${build_lang_options[@]}" "${java_build_tool_options[@]}" )
release_options=( "--snapshot" "${build_lang_options[@]}" "${java_build_tool_options[@]}" )
release_app_options=( "--build-docs", "--include-docs" "--no-build" "${release_options[@]}" )
build_options=( "--no-test" "${build_lang_options[@]}" "${java_build_tool_options[@]}" )
finalize_project_options=( "--no-commit" "${build_lang_options[@]}" "${java_build_tool_options[@]}" )
check_release_version_options=( "${build_lang_options[@]}" "${java_build_tool_options[@]}" )


if [[ "${DEBUG}" == "true" ]]; then
  set -x
fi
