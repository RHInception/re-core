%if 0%{?rhel} && 0%{?rhel} <= 6
%{!?__python2: %global __python2 /usr/bin/python2}
%{!?python2_sitelib: %global python2_sitelib %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%{!?python2_sitearch: %global python2_sitearch %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib(1))")}
%endif

%global _pkg_name recore

Name: re-core
Summary: FSM of the Inception Release Engine
Version: 0.0.2
Release: 1%{?dist}

Group: Applications/System
License: AGPLv3
Source0: %{name}-%{version}.tar.gz
Url: https://github.com/rhinception/re-core

BuildArch: noarch
BuildRequires: python2-devel
BuildRequires: python-setuptools
# BuildRequires: python-nose
# %{?el6:BuildRequires: python-unittest2}

%description
This is the core component of the Inception Release Engine. The core
is essentially a finite state machine hooked into a message bus and a
database.

The core oversees the execution of all release steps for any given
project. The core is separate from the actual execution of each
release step. Execution is delegated to the worker component.

# %check
# nosetests -v

%prep
%setup -q

%build
%{__python2} setup.py build

%install
%{__python2} setup.py install -O1 --root=$RPM_BUILD_ROOT --record=re-core-files.txt

%files -f re-core-files.txt
%dir %{python2_sitelib}/%{_pkg_name}
%{_bindir}/re-core
%doc README.md LICENSE AUTHORS

%changelog
* Fri Jun 6  2014 Ryan Cook <rcook@redhat.com> - 0.0.2-2
- Added python-setuptools

* Mon Apr 28 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.2-1
- Now with proper working state machine

* Tue Apr  8 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.1-1
- First release
