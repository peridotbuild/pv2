# Platform POC

A POC for builder nodes or developer purposes.

## Examples of pv2.util

```
[label@sani buildsys]$ python3
Python 3.11.3 (main, Apr  5 2023, 00:00:00) [GCC 13.0.1 20230401 (Red Hat 13.0.1-0)] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> from pv2.util import rpmutil
>>> rpm_header = rpmutil.get_rpm_header('/tmp/golang-1.19.4-1.el9.src.rpm')
>>> generic = rpmutil.get_rpm_metadata_from_hdr(rpm_header)
>>> generic['excludearch']
[]
>>> generic['exclusivearch']
['x86_64', 'aarch64', 'ppc64le', 's390x']

# Or the actual definition itself to skip the above
>>> rpmutil.get_exclu_from_package(rpm_header)
{'ExcludeArch': [], 'ExclusiveArch': ['x86_64', 'aarch64', 'ppc64le', 's390x']}
```

```
[label@sani buildsys]$ python3
Python 3.11.3 (main, Apr  5 2023, 00:00:00) [GCC 13.0.1 20230401 (Red Hat 13.0.1-0)] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> from pv2.util import rpmutil
>>> rpm_header = rpmputil.get_rpm_header('/tmp/rocky-release-8.9-1.4.el8.noarch.rpm')
>>> generic = rpmutil.get_rpm_metadata_from_hdr(rpm_header)
>>> generic.keys()
dict_keys(['changelog_xml', 'files', 'obsoletes', 'provides', 'conflicts', 'requires', 'vendor', 'buildhost', 'filetime', 'description', 'license', 'nvr', 'nevra', 'name', 'version', 'release', 'epoch', 'arch', 'archivesize', 'packagesize'])
>>> generic['buildhost']
'ord1-prod-a64build003.svc.aws.rockylinux.org'
>>> generic['description']
'Rocky Linux release files.'
>>> generic['nvr']
'rocky-release-8.9-1.4.el8'
>>> generic['files']
['/etc/centos-release', '/etc/issue', '/etc/issue.net', '/etc/os-release', '/etc/redhat-release', '/etc/rocky-release', '/etc/rocky-release-upstream', '/etc/system-release', '/etc/system-release-cpe', '/usr/lib/os-release', '/usr/lib/rpm/macros.d/macros.dist', '/usr/lib/systemd/system-preset/85-display-manager.preset', '/usr/lib/systemd/system-preset/90-default.preset', '/usr/lib/systemd/system-preset/99-default-disable.preset', '/usr/share/doc/rocky-release/COMMUNITY-CHARTER', '/usr/share/doc/rocky-release/Contributors', '/usr/share/licenses/rocky-release/LICENSE', '/usr/share/man/man1/rocky.1.gz', '/usr/share/redhat-release', '/usr/share/rocky-release/EULA']
```

## Examples of pv2.mock

```
[label@sani buildsys]$ python3
Python 3.11.3 (main, Apr  5 2023, 00:00:00) [GCC 13.0.1 20230401 (Red Hat 13.0.1-0)] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> from pv2.mock.config import DnfConfig, DnfRepoConfig, MockConfig, MockPluginConfig, MockChrootFileConfig, MockMacroFileConfig
>>> repo = DnfRepoConfig(repoid='devel', name='baseos', priority='99', baseurl='http://dl.rockylinux.org/pub/rocky/9/devel/x86_64/os', enabled=True, gpgcheck=False)
>>> repo_list = [repo]
>>> dnf_base_config = DnfConfig(repositories=repo_list)
>>> mock_config = MockConfig(root='rocky-9-x86_64-example', target_arch='x86_64', dist='.el9', distribution='Rocky Linux', dnf_config=dnf_base_config, releasever='9')
>>> mock_config.export_mock_config('/tmp/ex.cfg')

[label@sani buildsys]$ cat /tmp/ex.cfg
config_opts["root"] = "rocky-9-x86_64-example"
config_opts["chroot_setup_cmd"] = "install bash bzip2 coreutils cpio diffutils findutils gawk glibc-minimal-langpack grep gzip info make patch redhat-rpm-config rpm-build sed shadow-utils system-release tar unzip util-linux which xz"
config_opts["dist"] = "el9"
config_opts["legal_host_arches"] = ('x86_64',)
config_opts["macros"]["%_host"] = "x86_64-redhat-linux-gnu"
config_opts["macros"]["%_host_cpu"] = "x86_64"
config_opts["macros"]["%_rpmfilename"] = "%%{NAME}-%%{VERSION}-%%{RELEASE}.%%{ARCH}.rpm"
config_opts["macros"]["%_vendor"] = "redhat"
config_opts["macros"]["%_vendor_host"] = "redhat"
config_opts["macros"]["%packager"] = "Default Packager <packager@noone.home>"
config_opts["macros"]["%vendor"] = "Default Vendor"
config_opts["print_main_output"] = True
config_opts["releasever"] = "9"
config_opts["rpmbuild_networking"] = False
config_opts["target_arch"] = "x86_64"
config_opts["use_host_resolv"] = False
config_opts["files"]["/etc/rpm/macros.xx"] = """

%dist %{!?distprefix0:%{?distprefix}}%{expand:%{lua:for i=0,9999 do print("%{?distprefix" .. i .."}") end}}.el9%{?distsuffix}%{?with_bootstrap:~bootstrap}
%distribution Rocky Linux

"""

config_opts["dnf.conf"] = """
[main]
assumeyes=1
best=1
debuglevel=1
gpgcheck=0
install_weak_deps=0
keepcache=1
logfile=/var/log/yum.log
mdpolicy=group:primary
metadata_expire=0
obsoletes=1
protected_packages=
reposdir=/dev/null
retries=20
rpm_verbosity=info
syslog_device=
syslog_ident=peridotbuilder
user_agent=peridotbuilder

[devel]
baseurl=http://dl.rockylinux.org/pub/rocky/9/devel/x86_64/os
enabled=1
gpgcheck=0
name=baseos
priority=99
repoid=devel

"""
```
