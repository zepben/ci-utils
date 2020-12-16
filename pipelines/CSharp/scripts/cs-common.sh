if [[ $file == *".csproj" ]]; then
    version=$(xmlstarlet sel -t -v "/Project/PropertyGroup/Version" $file)
    sem_version=${version%-pre*}
elif [[ $file == *"AssemblyInfo.cs" ]]; then
    version=$(cat $file | grep "AssemblyVersion(\"[0-9]\+\.[0-9]\+\.[0-9]\+\")" | grep -o "[0-9]\+\.[0-9]\+\.[0-9]\+")
    sem_version=${version%-pre*}
fi

info "Version: $version"
info "Sem Version: $sem_version"

run_build() {
    if [[ $file != *".sln" ]]; then
        fail "Arg 1 must be a sln file."
    fi
    run dotnet restore $file --configfile /root/.dotnet/Nuget.Config
    run dotnet build $file -c Release --no-restore

    if [[ ! " ${options[@]} " =~ " --no-test " ]]; then
        run dotnet test $file --no-restore
    fi
}


deploy_lib(){
    debug "ZEPBEN_NUGET_UPLOAD_FEED=${ZEPBEN_NUGET_UPLOAD_FEED}"
    debug "ZEPBEN_NUGET_UPLOAD_KEY=${ZEPBEN_NUGET_UPLOAD_KEY}"
    debug "ZEPBEN_NUGET_FEED=${ZEPBEN_NUGET_FEED}"
    debug "ZEPBEN_NUGET_FEED_USERNAME=${ZEPBEN_NUGET_FEED_USERNAME}"
    debug "ZEPBEN_NUGET_FEED_PASSWORD=${ZEPBEN_NUGET_FEED_PASSWORD}"

    ZEPBEN_NUGET_UPLOAD_FEED=${ZEPBEN_NUGET_UPLOAD_FEED:?'Nuget upload source variable missing.'}
    ZEPBEN_NUGET_UPLOAD_KEY=${ZEPBEN_NUGET_UPLOAD_KEY:?'Nuget upload key variable missing.'}
    ZEPBEN_NUGET_FEED=${ZEPBEN_NUGET_FEED:?'Zepben Nuget feed variable missing.'}
    ZEPBEN_NUGET_FEED_USERNAME=${ZEPBEN_NUGET_FEED_USERNAME:?'Zepben Nuget feed username variable missing.'}
    ZEPBEN_NUGET_FEED_PASSWORD=${ZEPBEN_NUGET_FEED_PASSWORD:?'Zepben Nuget feed password variable missing.'}
    if [[ $file != *".csproj" ]]; then
        fail "Arg 1 must be a csproj file."
    fi

    if [[ " ${options[@]} " =~ " --snapshot " && $version != *"-pre"* ]]; then
        info "--snapshot option is only for non finalized. Skipping deployment."
        exit 0
    fi

    # Package
    info "Creating Nuget Package..."
    run dotnet restore $file --configfile /root/.dotnet/Nuget.Config
    run dotnet pack $file -c Release -o ./ --no-restore

    # Upload
    info "Uploading artifact..."
    dotnet nuget push *.nupkg -k $ZEPBEN_NUGET_UPLOAD_KEY -s $ZEPBEN_NUGET_UPLOAD_FEED
}

write_new_version(){
    old_ver=${1:? 'Old version is required.'}
    new_ver=${2:? 'New version is required.'}

    if [[ $old_ver != $new_ver ]]; then
        info "Writing new version $new_ver..."
        if [[ $file == *".csproj" ]]; then
            run xmlstarlet ed -P -L -u "/Project/PropertyGroup/Version" -v $new_ver $file
            if [[ $new_ver != *"-pre"* ]]; then
                run xmlstarlet ed -P -L -u "/Project/PropertyGroup/AssemblyVersion" -v "${new_ver}.0" $file
                run xmlstarlet ed -P -L -u "/Project/PropertyGroup/FileVersion" -v "${new_ver}.0" $file
            fi
        else
            sed -i "s/$old_ver/$new_ver/g" $file
        fi
    fi
}

update_version(){
    if [[ $file != *".csproj" && $file != *"AssemblyInfo.cs" ]]; then
        fail "Arg 1 must be a csproj file or AssemblyInfo.cs."
    fi
    incr_version $version_type $version
    if [[ $file == *".csproj" ]]; then
        new_version="${new_version}-pre1"
    fi
    write_new_version $version ${new_version}
}

update_snapshot_version(){
    if [[ $file != *".csproj" ]]; then
        fail "Arg 1 must be a csproj file."
    fi
    new_version=${version%-pre*}
    beta=${version##*-pre}
    beta=$((++beta))
    write_new_version $version "${new_version}-pre${beta}"
}

finalize_version(){
    new_version=${version%-pre*}
    write_new_version "$version" "$new_version"

    if [[ $file == *".cs" ]]; then
        info_version=$(cat $file | grep "AssemblyInformationalVersion(\"[0-9]\+\.[0-9]\+\.[0-9]\+.*\")" | grep -o "[0-9]\+\.[0-9]\+\.[0-9]\++build[0-9]\+")
        info_version_date=${info_version#*build}
        new_info_version_date=$(date '+%d%m%Y%H%M%S')
        info "Setting informational version to ${info_version%+build*}+build${new_info_version_date}"
        sed -i "s|$info_version_date|$new_info_version_date|g" $file
    fi
}

package(){
    fail "package for csharp not yet implemented."
}

check_release_version(){
    fail "Cs check_release_version Not implemented."
}