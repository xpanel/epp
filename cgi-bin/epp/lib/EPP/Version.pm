package EPP::Version;

###############################################################################
#
#	-------------------------
#			XPanel EPP Server
#		-------------------------
#
#	Version: 1.0.0
#	Web Site: http://www.xpanel.com/
#
#	(c) Copyright 2017 XPanel Ltd.
#
# *  XPanel Ltd. licenses this file to You under the Apache License, Version 2.0
# *  (the "License"); you may not use this file except in compliance with
# *  the License.  You may obtain a copy of the License at
# *
# *      http://www.apache.org/licenses/LICENSE-2.0
# *
# *  Unless required by applicable law or agreed to in writing, software
# *  distributed under the License is distributed on an "AS IS" BASIS,
# *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
###############################################################################



use strict;
use warnings;

BEGIN {
	use Exporter();
	our ($VERSION, @ISA, @EXPORT, @EXPORT_OK, %EXPORT_TAGS);

	$VERSION = do { my @r = (q$Revision: 1.01 $ =~ /\d+/g); sprintf "%d."."%02d" x $#r, @r};
	@ISA = qw(Exporter);
	@EXPORT = qw(SRS_VERSION SRS_REGISTRY_VERSION EPP_OBJURIS EPP_EXTENSIONS EPP_VERSIONS);
	@EXPORT_OK = qw();
	%EXPORT_TAGS = ();
}

our @EXPORT_OK;


# version numbers
our $_VERSION = '1.0';
our $_REGISTRY_VERSION = '1.0';
our @_EPP_VERSIONS = ( '1.0' );

# object URIs we support
our @_OBJURIS = (
	'urn:ietf:params:xml:ns:domain-1.0',
	'urn:ietf:params:xml:ns:contact-1.0',
	'urn:ietf:params:xml:ns:host-1.0',
	'http://www.verisign.com/epp/balance-1.0',
	'http://www.verisign.com/epp/lowbalance-poll-1.0',
	'http://www.verisign.com/epp/rgp-poll-1.0' );

our @_EXTENSIONS = (
	'urn:ietf:params:xml:ns:rgp-1.0',
	'urn:ietf:params:xml:ns:secDNS-1.1',
	'http://www.verisign.com/epp/idnLang-1.0',
	'http://www.nic.xx/XXNIC-EPP/identExt-1.0' );

sub SRS_VERSION {
	return ($_VERSION);
}

sub SRS_REGISTRY_VERSION {
	return ($_REGISTRY_VERSION);
}

sub EPP_OBJURIS {
	return (@_OBJURIS);
}

sub EPP_EXTENSIONS {
	return (@_EXTENSIONS);
}

sub EPP_VERSIONS {
	return (@_EPP_VERSIONS);
}

sub Version {
	return ({ VERSION => $_VERSION, REGISTRY_VERSION => $_REGISTRY_VERSION });
}

1;