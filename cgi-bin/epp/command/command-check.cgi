#!/usr/bin/perl

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



use lib '/var/www/cgi-bin/epp/lib';
use strict;
use warnings;
use EPP::Config();
use EPP::EPPWriter;
use CGI qw(:standard);
use XML::XPath;
use DBI;
use EPP::Date qw(:all);
use vars qw(%c $dbh $q);
*c = \%EPP::Config::c;
$q = new CGI;
$dbh = DBI->connect("DBI:mysql:$c{'mysql_database'}:$c{'mysql_host'}:$c{'mysql_port'}","$c{'mysql_username'}","$c{'mysql_password'}") or die "$DBI::errstr";

print header('application/epp+xml');

my $frame = $q->param('frame');
my $xp = XML::XPath->new(xml => $frame);

my $cltrid = $q->param('clTRID');
$cltrid = 'not-given' unless (defined($cltrid));
my $remote_user = $ENV{REMOTE_USER};


$xp->set_namespace('epp', 'urn:ietf:params:xml:ns:epp-1.0');
$xp->set_namespace('contact', 'urn:ietf:params:xml:ns:contact-1.0');
$xp->set_namespace('domain', 'urn:ietf:params:xml:ns:domain-1.0');
$xp->set_namespace('host', 'urn:ietf:params:xml:ns:host-1.0');

my $blob = {};
$blob->{clTRID} = $cltrid;
$blob->{resultCode} = 1000;
$blob->{cmd} = 'check';

my $node = $xp->findnodes('/epp:epp/epp:command/epp:check')->get_node(0);
my ($registrar_id) = $dbh->selectrow_array("SELECT `id` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

my $obj;
if ($obj = $xp->find('contact:check',$node)->get_node(0)) {
	################################################################
	#
	#			<check><contact:id>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-contact:check';
	$blob->{command} = 'check_contact';
	$blob->{obj_type} = 'contact';
	$blob->{ids} = [ ];

	my $nodeset_contact = $xp->find('contact:id', $obj);

	foreach my $node ($nodeset_contact->get_nodelist) {
		my $contact_id = $node->string_value;

		$contact_id = uc($contact_id);
		my $invalid_identifier = validate_identifier($contact_id);

		if ($invalid_identifier) {
			push (@{$blob->{ids}}, [ $contact_id, 1, $invalid_identifier ]);
		}
		else {
			my ($contact_id_already_exist) = $dbh->selectrow_array("SELECT `identifier` FROM `contact` WHERE `identifier` = '$contact_id' LIMIT 1");
			if ($contact_id_already_exist) {
				push (@{$blob->{ids}}, [ $contact_id_already_exist, 0, 'In use' ]);
			}
			else {
				push (@{$blob->{ids}}, [ $contact_id, 1 ]);
			}
		}
		$blob->{obj_id} .= $contact_id . "\n";
	}

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('domain:check',$node)->get_node(0)) {
	################################################################
	#
	#			<check><domain:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-domain:check';
	$blob->{command} = 'check_domain';
	$blob->{obj_type} = 'domain';
	$blob->{names} = [ ];

	my $nodeset_domain = $xp->find('domain:name', $obj);

	foreach my $node ($nodeset_domain->get_nodelist) {
		my $name = $node->string_value;

		$name = uc($name);
		my ($label,$domain_extension) = $name =~ /^([^\.]+)\.(.+)$/;
		my $invalid_domain = validate_label($label);

		# un while aici sa vedem daca numele de domeniu care se vrea inregistrat are extensia permisa de registry
		# selectam din cimpul tld, le facem cu litere mari apoi le comparam
		my $valid_tld = 0;
		my $sth = $dbh->prepare("SELECT `tld` FROM `domain_tld`") or die $dbh->errstr;
		$sth->execute() or die $sth->errstr;
		while (my ($tld) = $sth->fetchrow_array()) {
			$tld = uc($tld);
			my $ext = '.'.$domain_extension;
			if ($ext eq $tld) {
				$valid_tld = 1;
				last;
			}
		}
		$sth->finish;

		if ($invalid_domain || !$valid_tld) {
			push (@{$blob->{names}}, [ $name, 0, 'Bad domain name for registry.' ]);
		}
		else {
			my ($domain_name_already_exist) = $dbh->selectrow_array("SELECT `name` FROM `domain` WHERE `name` = '$name' LIMIT 1");
			if ($domain_name_already_exist) {
				push (@{$blob->{names}}, [ $domain_name_already_exist, 0, 'In use' ]);
			}
			else {
				my ($domain_name_already_reserved) = $dbh->selectrow_array("SELECT `name` FROM `reserved_domain_names` WHERE `name` = '$name' LIMIT 1");
				if ($domain_name_already_reserved) {
					push (@{$blob->{names}}, [ $domain_name_already_reserved, 0, 'Reserved or Restricted' ]);
				}
				else {
					push (@{$blob->{names}}, [ $name, 1 ]);
				}
			}
		}
		$blob->{obj_id} .= $name . "\n";
	}

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('host:check',$node)->get_node(0)) {
	################################################################
	#
	#			<check><host:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-host:check';
	$blob->{command} = 'check_host';
	$blob->{obj_type} = 'host';
	$blob->{names} = [ ];

	my $nodeset_host = $xp->find('host:name', $obj);

	foreach my $node ($nodeset_host->get_nodelist) {
		my $host_name = $node->string_value;

		$host_name = uc($host_name);
		#if ($host_name =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){0,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($host_name) < 254) {
		if ($host_name =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){1,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($host_name) < 254) {
			my ($host_name_already_exist) = $dbh->selectrow_array("SELECT `name` FROM `host` WHERE `name` = '$host_name' LIMIT 1");
			if ($host_name_already_exist) {
				push (@{$blob->{names}}, [ $host_name_already_exist, 0, 'In use' ]);
			}
			else {
				push (@{$blob->{names}}, [ $host_name, 1 ]);
			}
		}
		else {
			push (@{$blob->{names}}, [ $host_name, 0, 'Bad host name for registry' ]);
		}
		$blob->{obj_id} .= $host_name . "\n";
	}

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
else {
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-unknown:command';
	$blob->{command} = 'unknown';
	$blob->{resultCode} = 2001;
	$blob->{human_readable_message} = 'unknown command';
	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}


sub validate_identifier {
	my $identifier = shift;

	if (!$identifier) {
		return 'Abstract client and object identifier type minLength value=3';
	}

	if (length($identifier) < 3) {
		return 'Abstract client and object identifier type minLength value=3';
	}

	if (length($identifier) > 16) {
		return 'Abstract client and object identifier type maxLength value=16';
	}

	if ($identifier =~ /[^A-Z0-9\-]/) {
		return 'The ID of the contact must contain letters (A-Z) (ASCII) hyphen (-), and digits (0-9). Registry assigns each registrar a unique prefix with which that registrar must create contact IDs.';
	}
}


sub validate_label {
	my $label = shift;
	if (!$label) {
		return 'You must enter a domain name';
	}
	if (length($label) > 63) {
		return 'Total lenght of your domain must be less then 63 characters';
	}
	if (length($label) < 2) {
		return 'Total lenght of your domain must be greater then 2 characters';
	}
	if ($label =~ /[^A-Z0-9\-]/) {
		return 'Invalid domain name format';
	}
	if ($label =~ /^xn--/) {
		if ($label =~ /^-|-$|\.$/) {
			return 'Invalid domain name format, cannot begin or end with a hyphen (-)';
		}
	}
	else {
		if ($label =~ /^-|--|-$|\.$/) {
			return 'Invalid domain name format, cannot begin or end with a hyphen (-)';
		}
	}
}

sub update_transaction {
	my $svframe = shift;
	my $sth = $dbh->prepare("UPDATE `registryTransaction`.`transaction_identifier` SET `cmd` = ?, `obj_type` = ?, `obj_id` = ?, `code` = ?, `msg` = ?, `svTRID` = ?, `svTRIDframe` = ?, `svdate` = ?, `svmicrosecond` = ? WHERE `id` = ?") or die $dbh->errstr;
	my $date_for_sv_transaction = microsecond();
	my ($svdate,$svmicrosecond) = split(/\./, $date_for_sv_transaction);
	$sth->execute($blob->{cmd},$blob->{obj_type},$blob->{obj_id},$blob->{resultCode},$blob->{human_readable_message},$blob->{svTRID},$svframe,$svdate,$svmicrosecond,$transaction_id) or die $sth->errstr;
	return 1;
}