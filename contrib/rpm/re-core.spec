%if 0%{?rhel} && 0%{?rhel} <= 6
%{!?__python2: %global __python2 /usr/bin/python2}
%{!?python2_sitelib: %global python2_sitelib %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%{!?python2_sitearch: %global python2_sitearch %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib(1))")}
%endif

%global _pkg_name recore

Name: re-core
Summary: FSM of the Inception Release Engine
Version: 0.0.5
Release: 4%{?dist}

Group: Applications/System
License: AGPLv3
Source0: %{name}-%{version}.tar.gz
Url: https://github.com/rhinception/re-core

BuildArch: noarch
BuildRequires: python2-devel
BuildRequires: python-setuptools
Requires: python-pymongo
Requires: python-pika
Requires: python-argparse
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
rm -rf $RPM_BUILD_ROOT
%{__python2} setup.py install -O1 --root=$RPM_BUILD_ROOT --record=re-core-files.txt

%files -f re-core-files.txt
%defattr(-, root, root)
%dir %{python2_sitelib}/%{_pkg_name}
%{_bindir}/re-core
%doc README.md LICENSE AUTHORS examples/settings-example.json

%changelog
* Wed Nov 19 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.5-4
- Better handling for invalid/missing playbooks

* Tue Nov 18 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.5-3
- Ensure pre/post deploy stuff happens in defined order
- Closes DE7411

* Wed Nov  5 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.5-2
- And now per-release FSM instances connect over SSL

* Wed Nov  5 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.5-1
- Now with SSL connecting abilities

* Tue Oct 30 2014 Ryan Cook <rcook@redhat.com> - 0.0.4-6
- Creation of SSL request.

* Tue Oct  9 2014 Steve Milner <stevem@gnulinux.net> - 0.0.4-5
- Removed queue re-binding.

* Tue Oct  9 2014 Steve Milner <stevem@gnulinux.net> - 0.0.4-4
- Attempted fix for notification issues.
- Queues and Exchanges are no longer re-declared.

* Tue Oct 08 2014 Ryan Cook <rcook@redhat.com> - 0.0.4-3
- Version bump to include ability for FSM reconnection

* Tue Sep 23 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.4-2
- Now with POST_DEPLOY_ACTIONs

* Wed Aug 27 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.4-1
- Fix the routing key for notifications. Add logging

* Wed Aug 27 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.4-0
- Add code to support per-step notifications

* Mon Jul 21 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.3-8
- Now with pre-deployment checks

* Thu Jun 26 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.3-7
- Actually quit early when a step errors

* Thu Jun 26 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.3-6
- Properly abort if a worker errors/fails

* Mon Jun 24 2014 Ryan Cook <rcook@redhat.com> - 0.0.3-5
- Requires python-argparse

* Mon Jun 23 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.3-4
- Per-release logging functionality

* Fri Jun 20 2014 Steve Milner <stevem@gnulinux.net> - 0.0.3-3
- Bug fix in notification messages.

* Wed Jun 18 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.3-2
- Fix up RPM lint in packaging

* Wed Jun 18 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.3-1
- Loop over hosts by expanding the execution sequences

* Tue Jun 17 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.2-4
- Add missing Requires

* Fri Jun 13 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.2-3
- Send messages by topics rather than straight to queues

* Fri Jun 6  2014 Ryan Cook <rcook@redhat.com> - 0.0.2-2
- Added python-setuptools and fixed version

* Mon Apr 28 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.2-1
- Now with proper working state machine

* Tue Apr  8 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.1-1
- First release
