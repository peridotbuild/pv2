Name:           pv2
Version:        0.15.0
Release:        1%{?dist}
Summary:        pv2 importer module

License:        GPL-3.0-or-later
URL:            https://git.resf.org/peridot/pv2
Source0:        %{name}-%{version}.tar
#Source0:        https://git.resf.org/peridot/%{name}/archive/%{name}/%{version}.tar.gz

BuildArch:      noarch

%description
Provides the pv2 module

%package -n python3-%{name}
Summary: %{summary}
%{?python_provide:%python_provide python3-%{name}}

BuildRequires:  pkgconfig
BuildRequires:  bash-completion
BuildRequires:  git
Requires:       redhat-rpm-config
Requires:       python3-rpm

# This package redefines __python and can use the python_ macros
%global __python %{__python3}

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-cryptography
BuildRequires:  python3-GitPython
BuildRequires:  python3-pycurl
BuildRequires:  python3-yaml
BuildRequires:  python3-lxml
BuildRequires:  python3-boto3
BuildRequires:  python3-file-magic
BuildRequires:  python3-flit

Recommends:     rpm-build

%description -n python3-%{name}
%{description}

%package -n python3-%{name}-utils
Summary: %{summary}
Requires:       python3-%{name}

%description -n python3-%{name}-utils
%{description}

This contains the pv2 built-in utilities

%package -n srpmproc
Summary: Provides the srpmproc script
Requires:       python3-%{name}

%description -n srpmproc
%{description}

This contains the srpmproc script for performing Rocky Linux-esque imports.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install

%files -n python3-%{name}
%doc README.md
%license LICENSE
# For noarch packages: sitelib
%{python3_sitelib}/%{name}
%{python3_sitelib}/*.dist-info

%files -n python3-%{name}-utils
%{_bindir}/import_*

%files -n srpmproc
%{_bindir}/srpmproc

%changelog
* Wed Apr 30 2025 Louis Abel <label@resf.org> - 0.15.0-1
- Initial packaging of pv2
