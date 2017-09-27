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
use Email::Valid;
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
	$xp->set_namespace('identExt', 'http://www.nic.xx/XXNIC-EPP/identExt-1.0');

my $blob = {};
$blob->{clTRID} = $cltrid;
$blob->{resultCode} = 1000;
$blob->{cmd} = 'create';

my $node = $xp->findnodes('/epp:epp/epp:command/epp:create')->get_node(0);
	my $node_extension = $xp->findnodes('/epp:epp/epp:command/epp:extension')->get_node(0);
my ($registrar_id,$registrar_prefix) = $dbh->selectrow_array("SELECT `id`,`prefix` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

# EPP commands are atomic, so a command will either succeed completely or fail completely. Success and failure results MUST NOT be mixed.
my $obj;
	my $obj_ext;
if ($obj = $xp->find('contact:create',$node)->get_node(0)) {
	################################################################
	#
	#			<create><contact:id>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-contact:create';
	$blob->{command} = 'create_contact';
	$blob->{obj_type} = 'contact';

	# -  A <contact:id> element that contains the desired server-unique identifier for the contact to be created.
	my $identifier = $xp->findvalue('contact:id[1]', $obj);
	$blob->{obj_id} = $identifier;

	if (!$identifier) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Abstract client and object identifier type minLength value=3, maxLength value=16';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$identifier = uc($identifier);
	my $valid_identifier = validate_clIDType($identifier,'contact','contact:id');

	# Registry assigns each registrar a unique prefix with which that registrar must create contact IDs.
	if ($identifier !~ /^$registrar_prefix\-/) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = "Contact ID prefix must be '${registrar_prefix}-'. Registry assigns each registrar a unique prefix with which that registrar must create contact IDs.";
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:contact';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
			$blob->{obj_elem} = 'contact:id';
			$blob->{obj_elem_value} = $identifier;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($contact_id_already_exist) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$identifier' LIMIT 1");
	if ($contact_id_already_exist) {
		$blob->{resultCode} = 2302; # Object exists
		$blob->{human_readable_message} = 'Contact ID already exists';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}


	my $postalInfo_int = $xp->find('contact:postalInfo[@type=\'int\']', $obj)->get_node(0);
	# A <contact:name> element that contains the name of the individual or role represented by the contact.
	my $postalInfo_int_name = $xp->findvalue('contact:name[1]', $postalInfo_int);
	my $postalInfo_int_org = $xp->findvalue('contact:org[1]', $postalInfo_int);
	my $postalInfo_int_street_list = $xp->find('contact:addr/contact:street', $postalInfo_int);
	my @street_int;
	foreach my $node_int ($postalInfo_int_street_list->get_nodelist) {
		my $contact_street_int = $node_int->string_value;
		push(@street_int, $contact_street_int);
	}
	my $postalInfo_int_street1 = $street_int[0];
	my $postalInfo_int_street2 = $street_int[1] || '';
	my $postalInfo_int_street3 = $street_int[2] || '';
	# A <contact:city> element that contains the contact's city.
	my $postalInfo_int_city = $xp->findvalue('contact:addr/contact:city[1]', $postalInfo_int);
	my $postalInfo_int_sp = $xp->findvalue('contact:addr/contact:sp[1]', $postalInfo_int);
	my $postalInfo_int_pc = $xp->findvalue('contact:addr/contact:pc[1]', $postalInfo_int);
	# A <contact:cc> element that contains the contact's country code.
	my $postalInfo_int_cc = $xp->findvalue('contact:addr/contact:cc[1]', $postalInfo_int);

	if ($postalInfo_int) {
		if (!$postalInfo_int_name) {
			$blob->{resultCode} = 2003; # Required parameter missing
			$blob->{human_readable_message} = 'Missing contact:name';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:contact';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
				$blob->{obj_elem} = 'contact:name';
				$blob->{obj_elem_value} = $postalInfo_int_name;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($postalInfo_int_name =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_int_name !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Invalid contact:name';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:contact';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
				$blob->{obj_elem} = 'contact:name';
				$blob->{obj_elem_value} = $postalInfo_int_name;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($postalInfo_int_org) {
			if ($postalInfo_int_org =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_int_org !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:org';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:org';
					$blob->{obj_elem_value} = $postalInfo_int_org;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_int_street1) {
			if ($postalInfo_int_street1 =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_int_street1 !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:street';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:street';
					$blob->{obj_elem_value} = $postalInfo_int_street1;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_int_street2) {
			if ($postalInfo_int_street2 =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_int_street2 !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:street';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:street';
					$blob->{obj_elem_value} = $postalInfo_int_street2;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_int_street3) {
			if ($postalInfo_int_street3 =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_int_street3 !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:street';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:street';
					$blob->{obj_elem_value} = $postalInfo_int_street3;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_int_city =~ /(^\-)|(^\.)|(\-\-)|(\.\.)|(\.\-)|(\-\.)|(\-$)|(\.$)/ || $postalInfo_int_city !~ /^[a-z][a-z\-\.\s]{3,}$/i) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Invalid contact:city';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:contact';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
				$blob->{obj_elem} = 'contact:city';
				$blob->{obj_elem_value} = $postalInfo_int_city;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($postalInfo_int_sp) {
			if ($postalInfo_int_sp =~ /(^\-)|(^\.)|(\-\-)|(\.\.)|(\.\-)|(\-\.)|(\-$)|(\.$)/ || $postalInfo_int_sp !~ /^[A-Z][a-zA-Z\-\.\s]{1,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:sp';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:sp';
					$blob->{obj_elem_value} = $postalInfo_int_sp;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_int_pc) {
			if ($postalInfo_int_pc =~ /(^\-)|(\-\-)|(\-$)/ || $postalInfo_int_pc !~ /^[A-Z0-9\-\s]{3,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:pc';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:pc';
					$blob->{obj_elem_value} = $postalInfo_int_pc;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_int_cc !~ /^(AF|AX|AL|DZ|AS|AD|AO|AI|AQ|AG|AR|AM|AW|AU|AT|AZ|BS|BH|BD|BB|BY|BE|BZ|BJ|BM|BT|BO|BQ|BA|BW|BV|BR|IO|BN|BG|BF|BI|KH|CM|CA|CV|KY|CF|TD|CL|CN|CX|CC|CO|KM|CG|CD|CK|CR|CI|HR|CU|CW|CY|CZ|DK|DJ|DM|DO|EC|EG|SV|GQ|ER|EE|ET|FK|FO|FJ|FI|FR|GF|PF|TF|GA|GM|GE|DE|GH|GI|GR|GL|GD|GP|GU|GT|GG|GN|GW|GY|HT|HM|VA|HN|HK|HU|IS|IN|ID|IR|IQ|IE|IM|IL|IT|JM|JP|JE|JO|KZ|KE|KI|KP|KR|KW|KG|LA|LV|LB|LS|LR|LY|LI|LT|LU|MO|MK|MG|MW|MY|MV|ML|MT|MH|MQ|MR|MU|YT|MX|FM|MD|MC|MN|ME|MS|MA|MZ|MM|NA|NR|NP|NL|NC|NZ|NI|NE|NG|NU|NF|MP|NO|OM|PK|PW|PS|PA|PG|PY|PE|PH|PN|PL|PT|PR|QA|RE|RO|RU|RW|BL|SH|KN|LC|MF|PM|VC|WS|SM|ST|SA|SN|RS|SC|SL|SG|SX|SK|SI|SB|SO|ZA|GS|ES|LK|SD|SR|SJ|SZ|SE|CH|SY|TW|TJ|TZ|TH|TL|TG|TK|TO|TT|TN|TR|TM|TC|TV|UG|UA|AE|GB|US|UM|UY|UZ|VU|VE|VN|VG|VI|WF|EH|YE|ZM|ZW)$/) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Invalid contact:cc';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:contact';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
				$blob->{obj_elem} = 'contact:cc';
				$blob->{obj_elem_value} = $postalInfo_int_cc;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}


	my $postalInfo_loc = $xp->find('contact:postalInfo[@type=\'loc\']', $obj)->get_node(0);
	# A <contact:name> element that contains the name of the individual or role represented by the contact.
	my $postalInfo_loc_name = $xp->findvalue('contact:name[1]', $postalInfo_loc);
	my $postalInfo_loc_org = $xp->findvalue('contact:org[1]', $postalInfo_loc);
	my $postalInfo_loc_street_list = $xp->find('contact:addr/contact:street', $postalInfo_loc);
	my @street_loc;
	foreach my $node_loc ($postalInfo_loc_street_list->get_nodelist) {
		my $contact_street_loc = $node_loc->string_value;
		push(@street_loc, $contact_street_loc);
	}
	my $postalInfo_loc_street1 = $street_loc[0];
	my $postalInfo_loc_street2 = $street_loc[1] || '';
	my $postalInfo_loc_street3 = $street_loc[2] || '';
	# A <contact:city> element that contains the contact's city.
	my $postalInfo_loc_city = $xp->findvalue('contact:addr/contact:city[1]', $postalInfo_loc);
	my $postalInfo_loc_sp = $xp->findvalue('contact:addr/contact:sp[1]', $postalInfo_loc);
	my $postalInfo_loc_pc = $xp->findvalue('contact:addr/contact:pc[1]', $postalInfo_loc);
	# A <contact:cc> element that contains the contact's country code.
	my $postalInfo_loc_cc = $xp->findvalue('contact:addr/contact:cc[1]', $postalInfo_loc);

	if ($postalInfo_loc) {
		if (!$postalInfo_loc_name) {
			$blob->{resultCode} = 2003; # Required parameter missing
			$blob->{human_readable_message} = 'Missing contact:name';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:contact';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
				$blob->{obj_elem} = 'contact:name';
				$blob->{obj_elem_value} = $postalInfo_loc_name;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($postalInfo_loc_name =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_loc_name !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Invalid contact:name';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:contact';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
				$blob->{obj_elem} = 'contact:name';
				$blob->{obj_elem_value} = $postalInfo_loc_name;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($postalInfo_loc_org) {
			if ($postalInfo_loc_org =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_loc_org !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:org';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:org';
					$blob->{obj_elem_value} = $postalInfo_loc_org;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_loc_street1) {
			if ($postalInfo_loc_street1 =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_loc_street1 !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:street';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:street';
					$blob->{obj_elem_value} = $postalInfo_loc_street1;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_loc_street2) {
			if ($postalInfo_loc_street2 =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_loc_street2 !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:street';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:street';
					$blob->{obj_elem_value} = $postalInfo_loc_street2;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_loc_street3) {
			if ($postalInfo_loc_street3 =~ /(^\-)|(^\,)|(^\.)|(\-\-)|(\,\,)|(\.\.)|(\-$)/ || $postalInfo_loc_street3 !~ /^[a-zA-Z0-9\-\&\,\.\/\s]{5,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:street';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:street';
					$blob->{obj_elem_value} = $postalInfo_loc_street3;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_loc_city =~ /(^\-)|(^\.)|(\-\-)|(\.\.)|(\.\-)|(\-\.)|(\-$)|(\.$)/ || $postalInfo_loc_city !~ /^[a-z][a-z\-\.\s]{3,}$/i) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Invalid contact:city';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:contact';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
				$blob->{obj_elem} = 'contact:city';
				$blob->{obj_elem_value} = $postalInfo_loc_city;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($postalInfo_loc_sp) {
			if ($postalInfo_loc_sp =~ /(^\-)|(^\.)|(\-\-)|(\.\.)|(\.\-)|(\-\.)|(\-$)|(\.$)/ || $postalInfo_loc_sp !~ /^[A-Z][a-zA-Z\-\.\s]{1,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:sp';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:sp';
					$blob->{obj_elem_value} = $postalInfo_loc_sp;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_loc_pc) {
			if ($postalInfo_loc_pc =~ /(^\-)|(\-\-)|(\-$)/ || $postalInfo_loc_pc !~ /^[A-Z0-9\-\s]{3,}$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid contact:pc';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:contact';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
					$blob->{obj_elem} = 'contact:pc';
					$blob->{obj_elem_value} = $postalInfo_loc_pc;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		if ($postalInfo_loc_cc !~ /^(AF|AX|AL|DZ|AS|AD|AO|AI|AQ|AG|AR|AM|AW|AU|AT|AZ|BS|BH|BD|BB|BY|BE|BZ|BJ|BM|BT|BO|BQ|BA|BW|BV|BR|IO|BN|BG|BF|BI|KH|CM|CA|CV|KY|CF|TD|CL|CN|CX|CC|CO|KM|CG|CD|CK|CR|CI|HR|CU|CW|CY|CZ|DK|DJ|DM|DO|EC|EG|SV|GQ|ER|EE|ET|FK|FO|FJ|FI|FR|GF|PF|TF|GA|GM|GE|DE|GH|GI|GR|GL|GD|GP|GU|GT|GG|GN|GW|GY|HT|HM|VA|HN|HK|HU|IS|IN|ID|IR|IQ|IE|IM|IL|IT|JM|JP|JE|JO|KZ|KE|KI|KP|KR|KW|KG|LA|LV|LB|LS|LR|LY|LI|LT|LU|MO|MK|MG|MW|MY|MV|ML|MT|MH|MQ|MR|MU|YT|MX|FM|MD|MC|MN|ME|MS|MA|MZ|MM|NA|NR|NP|NL|NC|NZ|NI|NE|NG|NU|NF|MP|NO|OM|PK|PW|PS|PA|PG|PY|PE|PH|PN|PL|PT|PR|QA|RE|RO|RU|RW|BL|SH|KN|LC|MF|PM|VC|WS|SM|ST|SA|SN|RS|SC|SL|SG|SX|SK|SI|SB|SO|ZA|GS|ES|LK|SD|SR|SJ|SZ|SE|CH|SY|TW|TJ|TZ|TH|TL|TG|TK|TO|TT|TN|TR|TM|TC|TV|UG|UA|AE|GB|US|UM|UY|UZ|VU|VE|VN|VG|VI|WF|EH|YE|ZM|ZW)$/) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Invalid contact:cc';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:contact';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
				$blob->{obj_elem} = 'contact:cc';
				$blob->{obj_elem_value} = $postalInfo_loc_cc;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}

	if (!$postalInfo_int && !$postalInfo_loc) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Missing contact:postalInfo';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}


	# An OPTIONAL <contact:voice> element that contains the contact's voice telephone number.
	my $voice = $xp->findvalue('contact:voice[1]', $obj);
	my $voice_x = $xp->findvalue('contact:voice/@x[1]', $obj);
	if ($voice && ($voice !~ /^\+\d{1,3}\.\d{1,14}$/ || length($voice) > 17)) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Voice must be (\+[0-9]{1,3}\.[0-9]{1,14})';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:contact';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
			$blob->{obj_elem} = 'contact:voice';
			$blob->{obj_elem_value} = $voice;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# An OPTIONAL <contact:fax> element that contains the contact's facsimile telephone number.
	my $fax = $xp->findvalue('contact:fax[1]', $obj);
	my $fax_x = $xp->findvalue('contact:fax/@x[1]', $obj);
	if ($fax && ($fax !~ /^\+\d{1,3}\.\d{1,14}$/ || length($fax) > 17)) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Fax must be (\+[0-9]{1,3}\.[0-9]{1,14})';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:contact';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
			$blob->{obj_elem} = 'contact:fax';
			$blob->{obj_elem_value} = $fax;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# A <contact:email> element that contains the contact's email address.
	my $email = $xp->findvalue('contact:email[1]', $obj);
	#unless(Email::Valid->address(-address => $email, -mxcheck => 1)) {
	unless(Email::Valid->address($email)) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = "Email address failed $Email::Valid::Details check.";
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:contact';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
			$blob->{obj_elem} = 'contact:email';
			$blob->{obj_elem_value} = $email;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# A <contact:authInfo> element that contains authorization information to be associated with the contact object.
	my $authInfo_pw = $xp->findvalue('contact:authInfo/contact:pw[1]', $obj);
	#my $authInfo_ext = $xp->findvalue('contact:authInfo/contact:ext[1]', $obj);
	if (!$authInfo_pw) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Missing contact:pw';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:contact';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
			$blob->{obj_elem} = 'contact:authInfo';
			$blob->{obj_elem_value} = $authInfo_pw;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ((length($authInfo_pw) < 6) || (length($authInfo_pw) > 16)) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Password needs to be at least 6 and up to 16 characters long';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:contact';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
			$blob->{obj_elem} = 'contact:authInfo';
			$blob->{obj_elem_value} = $authInfo_pw;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ($authInfo_pw !~ /[A-Z]/) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Password should have both upper and lower case characters';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:contact';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
			$blob->{obj_elem} = 'contact:authInfo';
			$blob->{obj_elem_value} = $authInfo_pw;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

#	if ($authInfo_pw !~ /[a-z]/) {
#		$blob->{resultCode} = 2005; # Parameter value syntax error
#		$blob->{human_readable_message} = 'Password should have both upper and lower case characters';
#			$blob->{optionalValue} = 1;
#			$blob->{xmlns_obj} = 'xmlns:contact';
#			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
#			$blob->{obj_elem} = 'contact:authInfo';
#			$blob->{obj_elem_value} = $authInfo_pw;
#		my $msg = epp_writer($blob);
#		print $msg;
#		my $uptr = update_transaction($msg);
#		exit;
#	}

	if ($authInfo_pw !~ /\d/) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Password should contain one or more numbers';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:contact';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
			$blob->{obj_elem} = 'contact:authInfo';
			$blob->{obj_elem_value} = $authInfo_pw;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my $contact_disclose = $xp->find('contact:disclose', $obj);
	my $disclose_voice = 1;
	my $disclose_fax = 1;
	my $disclose_email = 1;
	my $disclose_name_int = 1;
	my $disclose_name_loc = 1;
	my $disclose_org_int = 1;
	my $disclose_org_loc = 1;
	my $disclose_addr_int = 1;
	my $disclose_addr_loc = 1;

	foreach my $node_disclose ($contact_disclose->get_nodelist) {
		my $flag = $xp->findvalue('@flag[1]', $node_disclose);	
		$disclose_voice = $flag if ($xp->find('contact:voice', $node_disclose)->size() > 0);
		$disclose_fax = $flag if ($xp->find('contact:fax', $node_disclose)->size() > 0);
		$disclose_email = $flag if ($xp->find('contact:email', $node_disclose)->size() > 0);
		$disclose_name_int = $flag if ($xp->find('contact:name[@type=\'int\']', $node_disclose)->size() > 0);
		$disclose_name_loc = $flag if ($xp->find('contact:name[@type=\'loc\']', $node_disclose)->size() > 0);
		$disclose_org_int = $flag if ($xp->find('contact:org[@type=\'int\']', $node_disclose)->size() > 0);
		$disclose_org_loc = $flag if ($xp->find('contact:org[@type=\'loc\']', $node_disclose)->size() > 0);
		$disclose_addr_int = $flag if ($xp->find('contact:addr[@type=\'int\']', $node_disclose)->size() > 0);
		$disclose_addr_loc = $flag if ($xp->find('contact:addr[@type=\'loc\']', $node_disclose)->size() > 0);
	}



	my $nin;
	my $nin_type;
	if ($obj_ext = $xp->find('identExt:create',$node_extension)->get_node(0)) {
		$nin = $xp->findvalue('identExt:nin[1]', $obj_ext)->value; # 1-16
		$nin_type = $xp->findvalue('identExt:nin/@type[1]', $obj_ext); # personal|business
		if ($nin !~ /\d/) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'NIN should contain one or more numbers';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
		if ($nin_type !~ /^(personal|business)$/) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'NIN Type should contain personal or business';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}



	# daca a trecut validarea creem un contact cu ID-ul dat de registrar
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	my $sth = $dbh->prepare("INSERT INTO `contact` (`identifier`,`voice`,`voice_x`,`fax`,`fax_x`,`email`,`nin`,`nin_type`,`clid`,`crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`disclose_voice`,`disclose_fax`,`disclose_email`) VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,?,?,?)") or die $dbh->errstr;
	$sth->execute($identifier,$voice || undef,$voice_x || undef,$fax || undef,$fax_x || undef,$email,$nin || undef,$nin_type || undef,$registrar_id,$registrar_id,$disclose_voice,$disclose_fax,$disclose_email) or die $sth->errstr;
	my $contact_id = $dbh->last_insert_id(undef, undef, undef, undef);

	if ($postalInfo_int) {
		$sth = $dbh->prepare("INSERT INTO `contact_postalInfo` (`contact_id`,`type`,`name`,`org`,`street1`,`street2`,`street3`,`city`,`sp`,`pc`,`cc`,`disclose_name_int`,`disclose_name_loc`,`disclose_org_int`,`disclose_org_loc`,`disclose_addr_int`,`disclose_addr_loc`) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)") or die $dbh->errstr;
		$sth->execute($contact_id,'int',$postalInfo_int_name,$postalInfo_int_org,$postalInfo_int_street1,$postalInfo_int_street2 || undef,$postalInfo_int_street3 || undef,$postalInfo_int_city,$postalInfo_int_sp,$postalInfo_int_pc,$postalInfo_int_cc,$disclose_name_int,$disclose_name_loc,$disclose_org_int,$disclose_org_loc,$disclose_addr_int,$disclose_addr_loc) or die $sth->errstr;
	}

	if ($postalInfo_loc) {
		$sth = $dbh->prepare("INSERT INTO `contact_postalInfo` (`contact_id`,`type`,`name`,`org`,`street1`,`street2`,`street3`,`city`,`sp`,`pc`,`cc`,`disclose_name_int`,`disclose_name_loc`,`disclose_org_int`,`disclose_org_loc`,`disclose_addr_int`,`disclose_addr_loc`) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)") or die $dbh->errstr;
		$sth->execute($contact_id,'loc',$postalInfo_loc_name,$postalInfo_loc_org,$postalInfo_loc_street1,$postalInfo_loc_street2 || undef,$postalInfo_loc_street3 || undef,$postalInfo_loc_city,$postalInfo_loc_sp,$postalInfo_loc_pc,$postalInfo_loc_cc,$disclose_name_int,$disclose_name_loc,$disclose_org_int,$disclose_org_loc,$disclose_addr_int,$disclose_addr_loc) or die $sth->errstr;
	}

	$sth = $dbh->prepare("INSERT INTO `contact_authInfo` (`contact_id`,`authtype`,`authinfo`) VALUES(?,?,?)") or die $dbh->errstr;
	$sth->execute($contact_id,'pw',$authInfo_pw) or die $sth->errstr;

	#if ($authInfo_ext) {
	#	$sth = $dbh->prepare("INSERT INTO `contact_authInfo` (`contact_id`,`authtype`,`authinfo`) VALUES(?,?,?)") or die $dbh->errstr;
	#	$sth->execute($contact_id,'ext',$authInfo_ext) or die $sth->errstr;
	#}

	my ($crdate) = $dbh->selectrow_array("SELECT `crdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");

	$blob->{id} = $identifier;
	$crdate =~ s/\s/T/g;
	$crdate .= '.0Z';
	$blob->{crDate} = $crdate;
	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('domain:create',$node)->get_node(0)) {
	################################################################
	#
	#			<create><domain:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-domain:create';
	$blob->{command} = 'create_domain';
	$blob->{obj_type} = 'domain';

	# -  A <domain:name> element that contains the fully qualified name of the domain object to be created.
	my $name = $xp->findvalue('domain:name[1]', $obj);
	$blob->{obj_id} = $name;

	$name = uc($name);
	my ($label,$domain_extension) = $name =~ /^([^\.]+)\.(.+)$/;
	my $invalid_domain = validate_label($label);

	if ($invalid_domain) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Invalid domain:name';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:name';
			$blob->{obj_elem_value} = $name;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# un while aici sa vedem daca numele de domeniu care se vrea inregistrat are extensia permisa de registry
	# selectam din cimpul tld, le facem cu litere mari apoi le comparam
	my $valid_tld = 0;
	my $tld_id;
	my $sth = $dbh->prepare("SELECT `id`,`tld` FROM `domain_tld`") or die $dbh->errstr;
	$sth->execute() or die $sth->errstr;
	while (my ($id,$tld) = $sth->fetchrow_array()) {
		$tld = uc($tld);
		my $ext = '.'.$domain_extension;
		if ($ext eq $tld) {
			$valid_tld = 1;
			$tld_id = $id;
			last;
		}
	}
	$sth->finish;

	if (!$valid_tld) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Invalid domain extension';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:name';
			$blob->{obj_elem_value} = $name;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($domain_already_exist) = $dbh->selectrow_array("SELECT `id` FROM `domain` WHERE `name` = '$name' LIMIT 1");
	if ($domain_already_exist) {
		$blob->{resultCode} = 2302; # Object exists
		$blob->{human_readable_message} = 'Domain name already exists';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($domain_already_reserved) = $dbh->selectrow_array("SELECT `id` FROM `reserved_domain_names` WHERE `name` = '$name' LIMIT 1");
	if ($domain_already_reserved) {
		$blob->{resultCode} = 2302; # Object exists
		$blob->{human_readable_message} = 'Domain name is reserved or restricted';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# -  An OPTIONAL <domain:period> element that contains the initial registration period of the domain object.  A server MAY define a default initial registration period if not specified by the client.
	my $period = $xp->findvalue('domain:period[1]', $obj)->value; # 1-99
	my $period_unit = $xp->findvalue('domain:period/@unit[1]', $obj); # m|y

	if ($period) {
		if (($period < 1) || ($period > 99)) {
			$blob->{resultCode} = 2004; # Parameter value range error
			$blob->{human_readable_message} = 'domain:period minLength value=1, maxLength value=99';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:domain';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
				$blob->{obj_elem} = 'domain:period';
				$blob->{obj_elem_value} = $period;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	else {
		# A server MAY define a default initial registration period if not specified by the client.
		$period = 1;
	}

	if ($period_unit) {
		if ($period_unit !~ /^(m|y)$/) {
			$blob->{resultCode} = 2004; # Parameter value range error
			$blob->{human_readable_message} = 'domain:period unit m|y';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	else {
		# A server MAY define a default initial registration period if not specified by the client.
		$period_unit = 'y';
	}

	my $date_add = 0;
	if ($period_unit eq 'y') {
		$date_add = ($period * 12);
	}
	elsif ($period_unit eq 'm') {
		$date_add = $period;
	}
	else {
		$date_add = $period;
	}

	# The number of units available MAY be subject to limits imposed by the server.
	# if (($date_add < 12) || ($date_add > 120)) {
	if ($date_add !~ /^(12|24|36|48|60|72|84|96|108|120)$/) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'A domain name can initially be registered for 1-10 years period';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:period';
			$blob->{obj_elem_value} = $period;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# aici facem o verificare daca are bani pe cont de deposit
	#_________________________________________________________________________________________________________________
	my ($registrar_balance,$creditLimit) = $dbh->selectrow_array("SELECT `accountBalance`,`creditLimit` FROM `registrar` WHERE `id` = '$registrar_id' LIMIT 1");
	my ($price) = $dbh->selectrow_array("SELECT `m$date_add` FROM `domain_price` WHERE `tldid` = '$tld_id' AND `command` = 'create' LIMIT 1");

	if (!defined($price)) {
		$blob->{resultCode} = 2400; # Command failed
		$blob->{human_readable_message} = 'Nu este declarat pretul, perioada si valuta pentru asa TLD';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if (($registrar_balance + $creditLimit) < $price) {
		$blob->{resultCode} = 2104; # Billing failure
		$blob->{human_readable_message} = 'Low credit: minimum threshold reached';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}
	#_________________________________________________________________________________________________________________





	# -  An OPTIONAL <domain:ns> element that contains the fully qualified names of the delegated host objects or host attributes.
	# Name servers are specified within a <domain:ns> element.  This element MUST contain one or more <domain:hostObj> elements or one or more <domain:hostAttr> elements.
	my $ns = $xp->find('domain:ns', $obj)->get_node(0);
	my $hostObj_list = $xp->find('domain:hostObj', $ns);
	my $hostAttr_list = $xp->find('domain:hostAttr', $ns);

	if (($hostObj_list->size() > 0) && ($hostAttr_list->size() > 0)) {
		$blob->{resultCode} = 2001; # Command syntax error
		$blob->{human_readable_message} = 'Nu poate fi in acelas timp hostObj si hostAttr, ori una ori alta';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

#	if (($hostObj_list->size() == 0) && ($hostAttr_list->size() == 0)) {
#		$blob->{resultCode} = 2001; # Command syntax error
#		$blob->{human_readable_message} = 'Nu este nimic in interiorul la domain:ns';
#		my $msg = epp_writer($blob);
#		print $msg;
#		my $uptr = update_transaction($msg);
#		exit;
#	}

	if ($hostObj_list->size() > 13) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu are voie mai mult de 13 domain:hostObj, deoarece RFC5730 nu impune limita';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:hostObj';
			$blob->{obj_elem_value} = $hostObj_list->get_node(14)->string_value;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ($hostAttr_list->size() > 13) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu are voie mai mult de 13 domain:hostAttr, deoarece RFC5730 nu impune limita';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:hostAttr';
			$blob->{obj_elem_value} = $hostAttr_list->get_node(14)->string_value;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# compare for duplicates list hostObj
	if ($hostObj_list->size() > 0) {
		my %nsArr;
		foreach my $node ($hostObj_list->get_nodelist) {
			my $hostObj = $node->string_value;
			if (exists($nsArr{$hostObj})) {
				# $hostObj se dubleaza
				$blob->{resultCode} = 2302; # Object exists
				$blob->{human_readable_message} = "Duplicate nameserver ($hostObj)";
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:domain';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
					$blob->{obj_elem} = 'domain:hostObj';
					$blob->{obj_elem_value} = $hostObj;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			$nsArr{$hostObj} = 1;
		}
	}

	# compare for duplicates list hostAttr
	if ($hostAttr_list->size() > 0) {
		my %nsArr;
		foreach my $node ($xp->find('domain:hostAttr/domain:hostName', $ns)->get_nodelist) {
			my $hostName = $node->string_value;
			if (exists($nsArr{$hostName})) {
				# $hostName se dubleaza
				$blob->{resultCode} = 2302; # Object exists
				$blob->{human_readable_message} = "Duplicate nameserver ($hostName)";
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:domain';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
					$blob->{obj_elem} = 'domain:hostName';
					$blob->{obj_elem_value} = $hostName;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			$nsArr{$hostName} = 1;
		}
	}

	if ($hostObj_list->size() > 0) {
		foreach my $node ($hostObj_list->get_nodelist) {
			my $hostObj = $node->string_value;
			$hostObj = uc($hostObj);
			if (($hostObj =~ /[^A-Z0-9\.\-]/) || ($hostObj =~ /^-|^\.|-\.|\.-|\.\.|-$|\.$/)) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid domain:hostObj';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:domain';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
					$blob->{obj_elem} = 'domain:hostObj';
					$blob->{obj_elem_value} = $hostObj;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}

			#if ($hostObj =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){0,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($hostObj) < 254) {
			if ($hostObj =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){1,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($hostObj) < 254) {
				# A host object MUST be known to the server before the host object can be associated with a domain object.
				my ($host_id_already_exist) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$hostObj' LIMIT 1");
				if (!$host_id_already_exist) {
					$blob->{resultCode} = 2303; # Object does not exist
					$blob->{human_readable_message} = "domain:hostObj $hostObj does not exist";
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
			}
			else {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid domain:hostObj !';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:domain';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
					$blob->{obj_elem} = 'domain:hostObj';
					$blob->{obj_elem_value} = $hostObj;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
	}

	if ($hostAttr_list->size() > 0) {
		foreach my $node ($hostAttr_list->get_nodelist) {
			my $hostName = $xp->findvalue('domain:hostName[1]', $node);
			$hostName = uc($hostName);
			if (($hostName =~ /[^A-Z0-9\.\-]/) || ($hostName =~ /^-|^\.|-\.|\.-|\.\.|-$|\.$/)) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid domain:hostName';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:domain';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
					$blob->{obj_elem} = 'domain:hostName';
					$blob->{obj_elem_value} = $hostName;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}

			# verificam daca hostul este external sau internal
			my $internal_host = 0;
			my $sth = $dbh->prepare("SELECT `tld` FROM `domain_tld`") or die $dbh->errstr;
			$sth->execute() or die $sth->errstr;
			while (my ($tld) = $sth->fetchrow_array()) {
				$tld = uc($tld);
				$tld =~ s/\./\\./g;
				if ($hostName =~ /$tld$/i) {
					$internal_host = 1;
					last;
				}
			}
			$sth->finish;

			if ($internal_host) {
				if ($hostName =~ /\.$name$/i) {
					# trebuie sa aiba adrese IP deoarece va exista superordinate domain

					my $hostAddr_list = $xp->find('domain:hostAddr', $node);
					# aici facem o verificare daca un host are mai mult de 13 adrese IP apoi reject
					# Max 13 IP per host.
					if ($hostAddr_list->size() > 13) {
						$blob->{resultCode} = 2306; # Parameter value policy error
						$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu are voie mai mult de 13 IP per host deoarece RFC5730 nu impune limita';
							$blob->{optionalValue} = 1;
							$blob->{xmlns_obj} = 'xmlns:domain';
							$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
							$blob->{obj_elem} = 'domain:hostAddr';
							$blob->{obj_elem_value} = $hostAddr_list->get_node(14)->string_value;
						my $msg = epp_writer($blob);
						print $msg;
						my $uptr = update_transaction($msg);
						exit;
					}

					# compare for duplicates list hostAddr
					if ($hostAddr_list->size() > 0) {
						my %nsArr;
						foreach my $node ($hostAddr_list->get_nodelist) {
							my $hostAddr = $node->string_value;
							if (exists($nsArr{$hostAddr})) {
								# $hostAddr se dubleaza
								$blob->{resultCode} = 2302; # Object exists
								$blob->{human_readable_message} = "Duplicate IP ($hostAddr)";
									$blob->{optionalValue} = 1;
									$blob->{xmlns_obj} = 'xmlns:domain';
									$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
									$blob->{obj_elem} = 'domain:hostAddr';
									$blob->{obj_elem_value} = $hostAddr;
								my $msg = epp_writer($blob);
								print $msg;
								my $uptr = update_transaction($msg);
								exit;
							}
							$nsArr{$hostAddr} = 1;
						}
					}
					else {
						# daca nu are adrese IP returnam error deoarece acest host este subordinate adica internal host
						$blob->{resultCode} = 2003; # Required parameter missing
						$blob->{human_readable_message} = 'Missing domain:hostAddr';
						my $msg = epp_writer($blob);
						print $msg;
						my $uptr = update_transaction($msg);
						exit;
					}

					foreach my $node ($hostAddr_list->get_nodelist) {
						my $hostAddr = $node->string_value;
						my $addr_type = $node->findvalue('@ip[1]') || 'v4';
						if ($addr_type eq 'v6') {
							if ($hostAddr =~ m/^[\da-fA-F]{1,4}(:[\da-fA-F]{1,4}){7}$/ || $hostAddr =~ m/^::$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){1,7}:$/ || $hostAddr =~ m/^[\da-fA-F]{1,4}:(:[\da-fA-F]{1,4}){1,6}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){2}(:[\da-fA-F]{1,4}){1,5}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){3}(:[\da-fA-F]{1,4}){1,4}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){4}(:[\da-fA-F]{1,4}){1,3}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){5}(:[\da-fA-F]{1,4}){1,2}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){6}:[\da-fA-F]{1,4}$/) {
								# true
								# Also note that the EPP registry may prohibit certain IP ranges from being used.
								# aici inca o verificare daca adresele nu sunt din cele rezervate sau private [RFC5735] [RFC5156]
							}
							else {
								$blob->{resultCode} = 2005; # Parameter value syntax error
								$blob->{human_readable_message} = 'Invalid domain:hostAddr v6';
									$blob->{optionalValue} = 1;
									$blob->{xmlns_obj} = 'xmlns:domain';
									$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
									$blob->{obj_elem} = 'domain:hostAddr';
									$blob->{obj_elem_value} = $hostAddr;
								my $msg = epp_writer($blob);
								print $msg;
								my $uptr = update_transaction($msg);
								exit;
							}
						}
						else {
							my ($a,$b,$c,$d) = split(/\./, $hostAddr, 4);
							if ($hostAddr =~ m/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/ && $a < 256 &&  $b < 256 && $c < 256 && $d < 256) {
								# true
								# Also note that the EPP registry may prohibit certain IP ranges from being used.
								# aici inca o verificare daca adresele nu sunt din cele rezervate sau private [RFC5735] [RFC5156]
								if ($hostAddr eq '127.0.0.1') {
									$blob->{resultCode} = 2005; # Parameter value syntax error
									$blob->{human_readable_message} = 'Invalid domain:hostAddr v4';
										$blob->{optionalValue} = 1;
										$blob->{xmlns_obj} = 'xmlns:domain';
										$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
										$blob->{obj_elem} = 'domain:hostAddr';
										$blob->{obj_elem_value} = $hostAddr;
									my $msg = epp_writer($blob);
									print $msg;
									my $uptr = update_transaction($msg);
									exit;
								}
							}
							else {
								$blob->{resultCode} = 2005; # Parameter value syntax error
								$blob->{human_readable_message} = 'Invalid domain:hostAddr v4';
									$blob->{optionalValue} = 1;
									$blob->{xmlns_obj} = 'xmlns:domain';
									$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
									$blob->{obj_elem} = 'domain:hostAddr';
									$blob->{obj_elem_value} = $hostAddr;
								my $msg = epp_writer($blob);
								print $msg;
								my $uptr = update_transaction($msg);
								exit;
							}
						}
					}
				}
				else {
					# verificam daca astfel de domeniu deja exista in registry, altfel nu putem sa creem un internal host pentru un domeniu inexistent
					if ($hostName =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){1,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($hostName) < 254) {
						my $domain_exist = 0;
						my $clid_domain = 0;
						my $sth = $dbh->prepare("SELECT `clid`,`name` FROM `domain`") or die $dbh->errstr;
						$sth->execute() or die $sth->errstr;
						while (my ($clid_of_existing_domain,$domain_name) = $sth->fetchrow_array()) {
							if ($hostName =~ /\.$domain_name$/i) {
								$domain_exist = 1;
								$clid_domain = $clid_of_existing_domain;
								last;
							}
						}
						$sth->finish;

						if (!$domain_exist) {
							$blob->{resultCode} = 2303; # Object does not exist
							$blob->{human_readable_message} = "domain:hostName $hostName . A host name object can NOT be created in a repository for which no superordinate domain name object exists.";
							my $msg = epp_writer($blob);
							print $msg;
							my $uptr = update_transaction($msg);
							exit;
						}

						# la fel daca acest domeniu apartine registrarului care vrea sa creeze hostul dat
						if ($registrar_id != $clid_domain) {
							$blob->{resultCode} = 2201; # Authorization error
							$blob->{human_readable_message} = 'Numele de domeniu apartine altui registrar, nu aveti permisiunea sa creati host-uri pentru el';
							my $msg = epp_writer($blob);
							print $msg;
							my $uptr = update_transaction($msg);
							exit;
						}
					}
					else {
						$blob->{resultCode} = 2005; # Parameter value syntax error
						$blob->{human_readable_message} = 'Invalid domain:hostName !!';
							$blob->{optionalValue} = 1;
							$blob->{xmlns_obj} = 'xmlns:domain';
							$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
							$blob->{obj_elem} = 'domain:hostName';
							$blob->{obj_elem_value} = $hostName;
						my $msg = epp_writer($blob);
						print $msg;
						my $uptr = update_transaction($msg);
						exit;
					}

					# trebuie sa aiba adrese IP exista superordinate domain
					my $hostAddr_list = $xp->find('domain:hostAddr', $node);
					# aici facem o verificare daca un host are mai mult de 13 adrese IP apoi reject
					# Max 13 IP per host.
					if ($hostAddr_list->size() > 13) {
						$blob->{resultCode} = 2306; # Parameter value policy error
						$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu are voie mai mult de 13 IP per host deoarece RFC5730 nu impune limita';
							$blob->{optionalValue} = 1;
							$blob->{xmlns_obj} = 'xmlns:domain';
							$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
							$blob->{obj_elem} = 'domain:hostAddr';
							$blob->{obj_elem_value} = $hostAddr_list->get_node(14)->string_value;
						my $msg = epp_writer($blob);
						print $msg;
						my $uptr = update_transaction($msg);
						exit;
					}

					# compare for duplicates list hostAddr
					if ($hostAddr_list->size() > 0) {
						my %nsArr;
						foreach my $node ($hostAddr_list->get_nodelist) {
							my $hostAddr = $node->string_value;
							if (exists($nsArr{$hostAddr})) {
								# $hostAddr se dubleaza
								$blob->{resultCode} = 2302; # Object exists
								$blob->{human_readable_message} = "Duplicate IP ($hostAddr)";
									$blob->{optionalValue} = 1;
									$blob->{xmlns_obj} = 'xmlns:domain';
									$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
									$blob->{obj_elem} = 'domain:hostAddr';
									$blob->{obj_elem_value} = $hostAddr;
								my $msg = epp_writer($blob);
								print $msg;
								my $uptr = update_transaction($msg);
								exit;
							}
							$nsArr{$hostAddr} = 1;
						}
					}
					else {
						# daca nu are adrese IP returnam error deoarece acest host este subordinate adica internal host, el trebuie sa aiba adrese IP
						$blob->{resultCode} = 2003; # Required parameter missing
						$blob->{human_readable_message} = 'Missing domain:hostAddr';
						my $msg = epp_writer($blob);
						print $msg;
						my $uptr = update_transaction($msg);
						exit;
					}

					foreach my $node ($hostAddr_list->get_nodelist) {
						my $hostAddr = $node->string_value;
						my $addr_type = $node->findvalue('@ip[1]') || 'v4';
						if ($addr_type eq 'v6') {
							if ($hostAddr =~ m/^[\da-fA-F]{1,4}(:[\da-fA-F]{1,4}){7}$/ || $hostAddr =~ m/^::$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){1,7}:$/ || $hostAddr =~ m/^[\da-fA-F]{1,4}:(:[\da-fA-F]{1,4}){1,6}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){2}(:[\da-fA-F]{1,4}){1,5}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){3}(:[\da-fA-F]{1,4}){1,4}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){4}(:[\da-fA-F]{1,4}){1,3}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){5}(:[\da-fA-F]{1,4}){1,2}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){6}:[\da-fA-F]{1,4}$/) {
								# true
								# Also note that the EPP registry may prohibit certain IP ranges from being used.
								# aici inca o verificare daca adresele nu sunt din cele rezervate sau private [RFC5735] [RFC5156]
							}
							else {
								$blob->{resultCode} = 2005; # Parameter value syntax error
								$blob->{human_readable_message} = 'Invalid domain:hostAddr v6';
									$blob->{optionalValue} = 1;
									$blob->{xmlns_obj} = 'xmlns:domain';
									$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
									$blob->{obj_elem} = 'domain:hostAddr';
									$blob->{obj_elem_value} = $hostAddr;
								my $msg = epp_writer($blob);
								print $msg;
								my $uptr = update_transaction($msg);
								exit;
							}
						}
						else {
							my ($a,$b,$c,$d) = split(/\./, $hostAddr, 4);
							if ($hostAddr =~ m/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/ && $a < 256 &&  $b < 256 && $c < 256 && $d < 256) {
								# true
								# Also note that the EPP registry may prohibit certain IP ranges from being used.
								# aici inca o verificare daca adresele nu sunt din cele rezervate sau private [RFC5735] [RFC5156]
								if ($hostAddr eq '127.0.0.1') {
									$blob->{resultCode} = 2005; # Parameter value syntax error
									$blob->{human_readable_message} = 'Invalid domain:hostAddr v4';
										$blob->{optionalValue} = 1;
										$blob->{xmlns_obj} = 'xmlns:domain';
										$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
										$blob->{obj_elem} = 'domain:hostAddr';
										$blob->{obj_elem_value} = $hostAddr;
									my $msg = epp_writer($blob);
									print $msg;
									my $uptr = update_transaction($msg);
									exit;
								}
							}
							else {
								$blob->{resultCode} = 2005; # Parameter value syntax error
								$blob->{human_readable_message} = 'Invalid domain:hostAddr v4';
									$blob->{optionalValue} = 1;
									$blob->{xmlns_obj} = 'xmlns:domain';
									$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
									$blob->{obj_elem} = 'domain:hostAddr';
									$blob->{obj_elem_value} = $hostAddr;
								my $msg = epp_writer($blob);
								print $msg;
								my $uptr = update_transaction($msg);
								exit;
							}
						}
					}
				}
			}
			else {
				# este external, nu ne trebuie adresele IP
				if ($hostName =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){1,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($hostName) < 254) {
					# o verificare daca el deja exista, daca exista apoi trebuie la hostObj dar nu hostattr
					# aici mai vedem, poate ca nu returnam nimica, doar ca la creare il atribuim in domain_host_map si gata
				}
				else {
					$blob->{resultCode} = 2005; # Parameter value syntax error
					$blob->{human_readable_message} = 'Invalid domain:hostName !!!';
						$blob->{optionalValue} = 1;
						$blob->{xmlns_obj} = 'xmlns:domain';
						$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
						$blob->{obj_elem} = 'domain:hostName';
						$blob->{obj_elem_value} = $hostName;
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
			}
		}
	}





	# -  An OPTIONAL <domain:registrant> element that contains the identifier for the human or organizational social information (contact) object to be associated with the domain object as the object registrant.
	my $registrant = $xp->findvalue('domain:registrant[1]', $obj);
	if ($registrant) {
		my $valid_registrant = validate_clIDType($registrant,'domain','domain:registrant');

		my ($registrant_id,$registrant_clid) = $dbh->selectrow_array("SELECT `id`,`clid` FROM `contact` WHERE `identifier` = '$registrant' LIMIT 1");
		if (!$registrant_id) {
			$blob->{resultCode} = 2303; # Object does not exist
			$blob->{human_readable_message} = 'domain:registrant does not exist';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($registrar_id != $registrant_clid) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'The contact requested in the command does NOT belong to the current Registrar';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}

	# -  Zero or more OPTIONAL <domain:contact type="admin"> elements that contain the identifiers for other contact objects to be associated with the domain object.
	my $contact_admin_list = $xp->find('domain:contact[@type=\'admin\']', $obj);

	# Max five admin contacts per domain name.
	if ($contact_admin_list->size() > 5) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu are voie mai mult de 5 admin contacts per domain name, deoarece RFC5730 nu impune limita';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:contact';
			$blob->{obj_elem_value} = $contact_admin_list->get_node(6)->string_value;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	foreach my $node ($contact_admin_list->get_nodelist) {
		my $contact_admin = $node->string_value;
		my $valid_contact_admin = validate_clIDType($contact_admin,'domain','domain:contact');

		my ($contact_admin_id,$contact_admin_clid) = $dbh->selectrow_array("SELECT `id`,`clid` FROM `contact` WHERE `identifier` = '$contact_admin' LIMIT 1");
		if (!$contact_admin_id) {
			$blob->{resultCode} = 2303; # Object does not exist
			$blob->{human_readable_message} = 'domain:contact type=admin does not exist';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($registrar_id != $contact_admin_clid) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'The contact type=admin requested in the command does NOT belong to the current Registrar';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}


	# -  Zero or more OPTIONAL <domain:contact type="billing"> elements that contain the identifiers for other contact objects to be associated with the domain object.
	my $contact_billing_list = $xp->find('domain:contact[@type=\'billing\']', $obj);
	# Max five billing contacts per domain name.
	if ($contact_billing_list->size() > 5) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu are voie mai mult de 5 billing contacts per domain name, deoarece RFC5730 nu impune limita';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:contact';
			$blob->{obj_elem_value} = $contact_billing_list->get_node(6)->string_value;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	foreach my $node ($contact_billing_list->get_nodelist) {
		my $contact_billing = $node->string_value;
		my $valid_contact_billing = validate_clIDType($contact_billing,'domain','domain:contact');

		my ($contact_billing_id,$contact_billing_clid) = $dbh->selectrow_array("SELECT `id`,`clid` FROM `contact` WHERE `identifier` = '$contact_billing' LIMIT 1");
		if (!$contact_billing_id) {
			$blob->{resultCode} = 2303; # Object does not exist
			$blob->{human_readable_message} = 'domain:contact type=billing does not exist';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($registrar_id != $contact_billing_clid) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'The contact type=billing requested in the command does NOT belong to the current Registrar';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}


	# -  Zero or more OPTIONAL <domain:contact type="tech"> elements that contain the identifiers for other contact objects to be associated with the domain object.
	my $contact_tech_list = $xp->find('domain:contact[@type=\'tech\']', $obj);
	# Max five tech contacts per domain name.
	if ($contact_tech_list->size() > 5) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu are voie mai mult de 5 tech contacts per domain name, deoarece RFC5730 nu impune limita';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:contact';
			$blob->{obj_elem_value} = $contact_tech_list->get_node(6)->string_value;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	foreach my $node ($contact_tech_list->get_nodelist) {
		my $contact_tech = $node->string_value;
		my $valid_contact_tech = validate_clIDType($contact_tech,'domain','domain:contact');

		my ($contact_tech_id,$contact_tech_clid) = $dbh->selectrow_array("SELECT `id`,`clid` FROM `contact` WHERE `identifier` = '$contact_tech' LIMIT 1");
		if (!$contact_tech_id) {
			$blob->{resultCode} = 2303; # Object does not exist
			$blob->{human_readable_message} = 'domain:contact type=tech does not exist';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($registrar_id != $contact_tech_clid) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'The contact type=tech requested in the command does NOT belong to the current Registrar';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}

	
	


	# -  A <domain:authInfo> element that contains authorization information to be associated with the domain object.	
	my $authInfo_pw = $xp->findvalue('domain:authInfo/domain:pw[1]', $obj);
	if (!$authInfo_pw) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Missing domain:pw';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:authInfo';
			$blob->{obj_elem_value} = $authInfo_pw;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ((length($authInfo_pw) < 6) || (length($authInfo_pw) > 16)) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Password needs to be at least 6 and up to 16 characters long';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:authInfo';
			$blob->{obj_elem_value} = $authInfo_pw;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ($authInfo_pw !~ /[A-Z]/) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Password should have both upper and lower case characters';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:authInfo';
			$blob->{obj_elem_value} = $authInfo_pw;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

#	if ($authInfo_pw !~ /[a-z]/) {
#		$blob->{resultCode} = 2005; # Parameter value syntax error
#		$blob->{human_readable_message} = 'Password should have both upper and lower case characters';
#			$blob->{optionalValue} = 1;
#			$blob->{xmlns_obj} = 'xmlns:domain';
#			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
#			$blob->{obj_elem} = 'domain:authInfo';
#			$blob->{obj_elem_value} = $authInfo_pw;
#		my $msg = epp_writer($blob);
#		print $msg;
#		my $uptr = update_transaction($msg);
#		exit;
#	}

	if ($authInfo_pw !~ /\d/) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Password should contain one or more numbers';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:authInfo';
			$blob->{obj_elem_value} = $authInfo_pw;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}






	my ($registrant_id) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$registrant' LIMIT 1");

	$sth = $dbh->prepare("INSERT INTO `domain` (`name`,`tldid`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`rgpstatus`,`addPeriod`) VALUES(?,?,?,CURRENT_TIMESTAMP,DATE_ADD(CURRENT_TIMESTAMP, INTERVAL ? MONTH),NULL,?,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'addPeriod',?)") or die $dbh->errstr;
	$sth->execute($name,$tld_id,$registrant_id,$date_add,$registrar_id,$registrar_id,$date_add) or die $sth->errstr;
	my $domain_id = $dbh->last_insert_id(undef, undef, undef, undef);

	$sth = $dbh->prepare("INSERT INTO `domain_authInfo` (`domain_id`,`authtype`,`authinfo`) VALUES(?,?,?)") or die $dbh->errstr;
	$sth->execute($domain_id,'pw',$authInfo_pw) or die $sth->errstr;

	#_________________________________________________________________________________________________________________
	$sth = $dbh->prepare("UPDATE `registrar` SET `accountBalance` = (`accountBalance` - ?) WHERE `id` = ?") or die $dbh->errstr;
	$sth->execute($price,$registrar_id) or die $sth->errstr;

	$sth = $dbh->prepare("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES(?,CURRENT_TIMESTAMP,'create domain $name for period $date_add MONTH',?)") or die $dbh->errstr;
	$sth->execute($registrar_id,"-$price") or die $sth->errstr;
	#_________________________________________________________________________________________________________________
	my ($from,$to) = $dbh->selectrow_array("SELECT `crdate`,`exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
	$sth = $dbh->prepare("INSERT INTO `statement` (`registrar_id`,`date`,`command`,`domain_name`,`length_in_months`,`from`,`to`,`amount`) VALUES(?,CURRENT_TIMESTAMP,?,?,?,?,?,?)") or die $dbh->errstr;
	$sth->execute($registrar_id,$blob->{cmd},$name,$date_add,$from,$to,$price) or die $sth->errstr;
	#_________________________________________________________________________________________________________________

	foreach my $node ($hostObj_list->get_nodelist) {
		my $hostObj = $node->string_value;
		$hostObj = uc($hostObj);
		# A host object MUST be known to the server before the host object can be associated with a domain object.
		my ($hostObj_already_exist) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$hostObj' LIMIT 1");
		if ($hostObj_already_exist) {
			my ($domain_host_map_id) = $dbh->selectrow_array("SELECT `domain_id` FROM `domain_host_map` WHERE `domain_id` = '$domain_id' AND `host_id` = '$hostObj_already_exist' LIMIT 1");
			if (!$domain_host_map_id) {
				$sth = $dbh->prepare("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES(?,?)") or die $dbh->errstr;
				$sth->execute($domain_id,$hostObj_already_exist) or die $sth->errstr;
			}
			else {
				# cred ca el aici o indicat ceva care se dubleaza, mai rare cazuri dar totusi
				$dbh->do("INSERT INTO `error_log` (`registrar_id`,`log`,`date`) VALUES('$registrar_id','Domain : $name ;   hostObj : $hostObj - se dubleaza',CURRENT_TIMESTAMP)") or die $dbh->errstr;
			}
		}
		else {
			# acest caz nu ar trebui sa existe, dar daca totusi exista, atunci repartizam cum trebuie, dar nu avem adresa IP
			# facem o verificare, daca acest hostObj are TLD din acest registry, daca asa domeniu nu exista inregistrat si e diferit decit cel ce se vrea inregistrat acuma, dam eroare
			# selectam din cimpul tld, le facem cu litere mari apoi le comparam
			my $internal_host = 0;
			my $sth = $dbh->prepare("SELECT `tld` FROM `domain_tld`") or die $dbh->errstr;
			$sth->execute() or die $sth->errstr;
			while (my ($tld) = $sth->fetchrow_array()) {
				$tld = uc($tld);
				$tld =~ s/\./\\./g;
				if ($hostObj =~ /$tld$/i) {
					$internal_host = 1;
					last;
				}
			}
			$sth->finish;


			if ($internal_host) {
				if ($hostObj =~ /\.$name$/i) {
					$sth = $dbh->prepare("INSERT INTO `host` (`name`,`domain_id`,`clid`,`crid`,`crdate`) VALUES(?,?,?,?,CURRENT_TIMESTAMP)") or die $dbh->errstr;
					$sth->execute($hostObj,$domain_id,$registrar_id,$registrar_id) or die $sth->errstr;
					my $host_id = $dbh->last_insert_id(undef, undef, undef, undef);

					$sth = $dbh->prepare("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES(?,?)") or die $dbh->errstr;
					$sth->execute($domain_id,$host_id) or die $sth->errstr;
				}
			}
			else {
				$sth = $dbh->prepare("INSERT INTO `host` (`name`,`clid`,`crid`,`crdate`) VALUES(?,?,?,CURRENT_TIMESTAMP)") or die $dbh->errstr;
				$sth->execute($hostObj,$registrar_id,$registrar_id) or die $sth->errstr;
				my $host_id = $dbh->last_insert_id(undef, undef, undef, undef);

				$sth = $dbh->prepare("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES(?,?)") or die $dbh->errstr;
				$sth->execute($domain_id,$host_id) or die $sth->errstr;
			}
		}
	}





	foreach my $node ($hostAttr_list->get_nodelist) {
		my $hostName = $xp->findvalue('domain:hostName[1]', $node);
		$hostName = uc($hostName);
		my ($hostName_already_exist) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$hostName' LIMIT 1");
		if ($hostName_already_exist) {
			my ($domain_host_map_id) = $dbh->selectrow_array("SELECT `domain_id` FROM `domain_host_map` WHERE `domain_id` = '$domain_id' AND `host_id` = '$hostName_already_exist' LIMIT 1");
			if (!$domain_host_map_id) {
				$sth = $dbh->prepare("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES(?,?)") or die $dbh->errstr;
				$sth->execute($domain_id,$hostName_already_exist) or die $sth->errstr;
			}
			else {
				# cred ca el aici o indicat ceva care se dubleaza, mai rare cazuri dar totusi
				$dbh->do("INSERT INTO `error_log` (`registrar_id`,`log`,`date`) VALUES('$registrar_id','Domain : $name ;   hostName : $hostName - se dubleaza',CURRENT_TIMESTAMP)") or die $dbh->errstr;
			}
		}
		else {
			$sth = $dbh->prepare("INSERT INTO `host` (`name`,`domain_id`,`clid`,`crid`,`crdate`) VALUES(?,?,?,?,CURRENT_TIMESTAMP)") or die $dbh->errstr;
			$sth->execute($hostName,$domain_id,$registrar_id,$registrar_id) or die $sth->errstr;
			my $host_id = $dbh->last_insert_id(undef, undef, undef, undef);

			$sth = $dbh->prepare("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES(?,?)") or die $dbh->errstr;
			$sth->execute($domain_id,$host_id) or die $sth->errstr;

			my $hostAddr_list = $xp->find('domain:hostAddr', $node);
			foreach my $node ($hostAddr_list->get_nodelist) {
				my $hostAddr = $node->string_value;
				my $addr_type = $node->findvalue('@ip[1]') || 'v4';

				# normalise
				if ($addr_type eq 'v6') {
					$hostAddr = _normalise_v6_address($hostAddr);
				}
				else {
					$hostAddr = _normalise_v4_address($hostAddr);
				}

				$sth = $dbh->prepare("INSERT INTO `host_addr` (`host_id`,`addr`,`ip`) VALUES(?,?,?)") or die $dbh->errstr;
				$sth->execute($host_id,$hostAddr,$addr_type) or die $sth->errstr;
			}
		}
	}



	foreach my $node ($contact_admin_list->get_nodelist) {
		my $contact_admin = $node->string_value;
		my ($contact_admin_id) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$contact_admin' LIMIT 1");
		$sth = $dbh->prepare("INSERT INTO `domain_contact_map` (`domain_id`,`contact_id`,`type`) VALUES(?,?,?)") or die $dbh->errstr;
		$sth->execute($domain_id,$contact_admin_id,'admin') or die $sth->errstr;
	}

	foreach my $node ($contact_billing_list->get_nodelist) {
		my $contact_billing = $node->string_value;
		my ($contact_billing_id) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$contact_billing' LIMIT 1");
		$sth = $dbh->prepare("INSERT INTO `domain_contact_map` (`domain_id`,`contact_id`,`type`) VALUES(?,?,?)") or die $dbh->errstr;
		$sth->execute($domain_id,$contact_billing_id,'billing') or die $sth->errstr;
	}

	foreach my $node ($contact_tech_list->get_nodelist) {
		my $contact_tech = $node->string_value;
		my ($contact_tech_id) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$contact_tech' LIMIT 1");
		$sth = $dbh->prepare("INSERT INTO `domain_contact_map` (`domain_id`,`contact_id`,`type`) VALUES(?,?,?)") or die $dbh->errstr;
		$sth->execute($domain_id,$contact_tech_id,'tech') or die $sth->errstr;
	}

	my ($crdate,$exdate) = $dbh->selectrow_array("SELECT `crdate`,`exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");

	my $curdate_id = $dbh->selectrow_array("SELECT `id` FROM `statistics` WHERE `date` = CURDATE()");
	if (!$curdate_id) {
		$dbh->do("INSERT IGNORE INTO `statistics` (`date`) VALUES(CURDATE())") or die $dbh->errstr;
	}
	$dbh->do("UPDATE `statistics` SET `created_domains` = `created_domains` + 1 WHERE `date` = CURDATE()") or die $dbh->errstr;

	$blob->{name} = $name;
	$crdate =~ s/\s/T/g;
	$crdate .= '.0Z';
	$blob->{crDate} = $crdate;
	$exdate =~ s/\s/T/g;
	$exdate .= '.0Z';
	$blob->{exDate} = $exdate;
	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('host:create',$node)->get_node(0)) {
	################################################################
	#
	#			<create><host:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-host:create';
	$blob->{command} = 'create_host';
	$blob->{obj_type} = 'host';

	# -  A <host:name> element that contains the fully qualified name of the host object to be created.
	my $name = $xp->findvalue('host:name[1]', $obj);
	$blob->{obj_id} = $name;

	$name = uc($name);
	#if ($name =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){0,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($name) < 254) {
	if ($name =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){1,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($name) < 254) {
		my ($host_id_already_exist) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$name' LIMIT 1");
		if ($host_id_already_exist) {
			$blob->{resultCode} = 2302; # Object exists
			$blob->{human_readable_message} = 'host:name already exists';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	else {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Invalid host:name';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:host';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:host-1.0';
			$blob->{obj_elem} = 'host:name';
			$blob->{obj_elem_value} = $name;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}





	# -  Zero or more <host:addr> elements that contain the IP addresses to be associated with the host.
	my $host_addr_list = $xp->find('host:addr', $obj);
	if ($host_addr_list->size() > 13) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu are voie mai mult de 13 host:addr, deoarece RFC5730 nu impune limita';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:host';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:host-1.0';
			$blob->{obj_elem} = 'host:addr';
			$blob->{obj_elem_value} = $host_addr_list->get_node(14)->string_value;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my %nsArr;
	foreach my $node ($host_addr_list->get_nodelist) {
		my $addr = $node->string_value;
		my $addr_type = $node->findvalue('@ip[1]') || 'v4';

		# normalise
		if ($addr_type eq 'v6') {
			$addr = _normalise_v6_address($addr);
		}
		else {
			$addr = _normalise_v4_address($addr);
		}

		if ($addr_type eq 'v6') {
			if ($addr =~ m/^[\da-fA-F]{1,4}(:[\da-fA-F]{1,4}){7}$/ || $addr =~ m/^::$/ || $addr =~ m/^([\da-fA-F]{1,4}:){1,7}:$/ || $addr =~ m/^[\da-fA-F]{1,4}:(:[\da-fA-F]{1,4}){1,6}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){2}(:[\da-fA-F]{1,4}){1,5}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){3}(:[\da-fA-F]{1,4}){1,4}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){4}(:[\da-fA-F]{1,4}){1,3}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){5}(:[\da-fA-F]{1,4}){1,2}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){6}:[\da-fA-F]{1,4}$/) {
				# true
				# Also note that the EPP registry may prohibit certain IP ranges from being used.
			}
			else {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid host:addr v6';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:host';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:host-1.0';
					$blob->{obj_elem} = 'host:addr';
					$blob->{obj_elem_value} = $addr;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
		else {
			my ($a,$b,$c,$d) = split(/\./, $addr, 4);
			if ($addr =~ m/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/ && $a < 256 &&  $b < 256 && $c < 256 && $d < 256) {
				# true
				# Also note that the EPP registry may prohibit certain IP ranges from being used.
				if ($addr eq '127.0.0.1') {
					$blob->{resultCode} = 2005; # Parameter value syntax error
					$blob->{human_readable_message} = 'Invalid host:addr v4';
						$blob->{optionalValue} = 1;
						$blob->{xmlns_obj} = 'xmlns:host';
						$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:host-1.0';
						$blob->{obj_elem} = 'host:addr';
						$blob->{obj_elem_value} = $addr;
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
			}
			else {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Invalid host:addr v4';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:host';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:host-1.0';
					$blob->{obj_elem} = 'host:addr';
					$blob->{obj_elem_value} = $addr;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		# aici va fi verificare cu duplicate la IP
		if (exists($nsArr{$addr})) {
			# $addr se dubleaza
			$blob->{resultCode} = 2302; # Object exists
			$blob->{human_readable_message} = "Duplicate IP ($addr)";
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns:host';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:host-1.0';
				$blob->{obj_elem} = 'host:addr';
				$blob->{obj_elem_value} = $addr;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
		$nsArr{$addr} = 1;
	}




	# If the host name exists in a namespace for which the server is authoritative, then the superordinate domain of the host MUST be known to the server before the host object can be created.
	# un while aici sa vedem daca hostul care se vrea inregistrat are extensia din acest registru
	# selectam din cimpul tld, le facem cu litere mai apoi le comparam
	my $internal_host = 0;
	my $sth = $dbh->prepare("SELECT `tld` FROM `domain_tld`") or die $dbh->errstr;
	$sth->execute() or die $sth->errstr;
	while (my ($tld) = $sth->fetchrow_array()) {
		$tld = uc($tld);
		$tld =~ s/\./\\./g;
		if ($name =~ /$tld$/i) {
			$internal_host = 1;
			last;
		}
	}
	$sth->finish;




	# If the host name exists in a namespace for which the server is authoritative, then the superordinate domain of the host MUST be known to the server before the host object can be created.
	# daca registrul dat accepta domenii .XX apoi inregistrarea hostului NS1.EXEMPLU.XX este posibil doar daca exista deja inregistrat domeniul EXEMPLU.XX
	if ($internal_host) {
		# verificam daca astfel de domeniu deja exista in registry, altfel nu putem sa creem un internal host pentru un domeniu inexistent
		my $domain_exist = 0;
		my $clid_domain = 0;
		my $superordinate_dom = 0;
		my $sth = $dbh->prepare("SELECT `id`,`clid`,`name` FROM `domain`") or die $dbh->errstr;
		$sth->execute() or die $sth->errstr;
		while (my ($superordinate_domain_of_the_host_id,$clid_of_existing_domain,$domain_name) = $sth->fetchrow_array()) {
			if ($name =~ /\.$domain_name$/i) {
				$domain_exist = 1;
				$clid_domain = $clid_of_existing_domain;
				$superordinate_dom = $superordinate_domain_of_the_host_id;
				last;
			}
		}
		$sth->finish;

		if (!$domain_exist) {
			$blob->{resultCode} = 2303; # Object does not exist
			$blob->{human_readable_message} = "Nu este superordinate domain. A host name object can NOT be created in a repository for which no superordinate domain name object exists.";
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# la fel daca acest domeniu apartine registrarului care vrea sa creeze hostul dat
		if ($registrar_id != $clid_domain) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'Numele de domeniu apartine altui registrar, nu aveti permisiunea sa creati host-uri pentru el';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		$sth = $dbh->prepare("INSERT INTO `host` (`name`,`domain_id`,`clid`,`crid`,`crdate`) VALUES(?,?,?,?,CURRENT_TIMESTAMP)") or die $dbh->errstr;
		$sth->execute($name,$superordinate_dom,$registrar_id,$registrar_id) or die $sth->errstr;
		my $host_id = $dbh->last_insert_id(undef, undef, undef, undef);

		my $host_addr_list = $xp->find('host:addr', $obj);
		foreach my $node ($host_addr_list->get_nodelist) {
			my $addr = $node->string_value;
			my $addr_type = $node->findvalue('@ip[1]') || 'v4';

			# normalise
			if ($addr_type eq 'v6') {
				$addr = _normalise_v6_address($addr);
			}
			else {
				$addr = _normalise_v4_address($addr);
			}

			# v4 => 4; v6 => 6
			$addr_type =~ s/\D//g;

			# aici nu pot fi dubluri, noi de fapt am verificat mai sus daca adresele IP nu se dubleaza, dar mai stii poate dupa normalizare unele se aseamana
			my $sth = $dbh->prepare("INSERT INTO `host_addr` (`host_id`,`addr`,`ip`) VALUES(?,?,?)") or die $dbh->errstr;
			$sth->execute($host_id,$addr,$addr_type) or die $sth->errstr;
		}

		my ($crdate) = $dbh->selectrow_array("SELECT `crdate` FROM `host` WHERE `name` = '$name' LIMIT 1");
		$blob->{name} = $name;
		$crdate =~ s/\s/T/g;
		$crdate .= '.0Z';
		$blob->{crDate} = $crdate;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
	}
	else {
		$sth = $dbh->prepare("INSERT INTO `host` (`name`,`clid`,`crid`,`crdate`) VALUES(?,?,?,CURRENT_TIMESTAMP)") or die $dbh->errstr;
		$sth->execute($name,$registrar_id,$registrar_id) or die $sth->errstr;
		my $host_id = $dbh->last_insert_id(undef, undef, undef, undef);

		my ($crdate) = $dbh->selectrow_array("SELECT `crdate` FROM `host` WHERE `name` = '$name' LIMIT 1");
		$blob->{name} = $name;
		$crdate =~ s/\s/T/g;
		$crdate .= '.0Z';
		$blob->{crDate} = $crdate;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
	}
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

sub validate_clIDType {
	my $identifier = shift;
	my $obj = shift;
	my $elem = shift;

	if (length($identifier) < 3) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Abstract client and object identifier type minLength value=3';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = "xmlns:$obj";
			$blob->{xmlns_obj_value} = "urn:ietf:params:xml:ns:$obj-1.0";
			$blob->{obj_elem} = $elem;
			$blob->{obj_elem_value} = $identifier;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}
	if (length($identifier) > 16) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Abstract client and object identifier type maxLength value=16';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = "xmlns:$obj";
			$blob->{xmlns_obj_value} = "urn:ietf:params:xml:ns:$obj-1.0";
			$blob->{obj_elem} = $elem;
			$blob->{obj_elem_value} = $identifier;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}
	if ($identifier =~ /[^A-Z0-9\-]/) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'The ID of the contact must contain letters (A-Z) (ASCII) hyphen (-), and digits (0-9)';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = "xmlns:$obj";
			$blob->{xmlns_obj_value} = "urn:ietf:params:xml:ns:$obj-1.0";
			$blob->{obj_elem} = $elem;
			$blob->{obj_elem_value} = $identifier;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}
	if ($identifier =~ /^-|--|-$|\.$/) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'The ID of the contact cannot begin or end with a hyphen (-)';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = "xmlns:$obj";
			$blob->{xmlns_obj_value} = "urn:ietf:params:xml:ns:$obj-1.0";
			$blob->{obj_elem} = $elem;
			$blob->{obj_elem_value} = $identifier;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	return 1;
}


sub _normalise_v4_address {
	my ($v4) = @_;

	$v4 =~ s/^0+(\d)/$1/;			# remove leading zeros from the first octet
	$v4 =~ s/\.0+(\d)/.$1/g;		# remove leading zeros from successive octets

	return ($v4);
}


sub _normalise_v6_address {
	my ($v6) = @_;

	$v6 =~ uc($v6);					# upper case any alphabetics
	$v6 =~ s/^0+([\dA-F])/$1/;		# remove leading zeros from the first word
	$v6 =~ s/:0+([\dA-F])/:$1/g;	# remove leading zeros from successive words

	$v6 =~ s/:0:0:/::/
	unless ($v6 =~ m/::/);			# introduce a :: if there isn't one already

	$v6 =~ s/^0+::/::/;				# remove initial zero word before a ::
	$v6 =~ s/(:0)+::/::/;			# remove other zero words before a ::
	$v6 =~ s/:(:0)+/:/;				# remove zero words following a ::

	return ($v6);
}

sub update_transaction {
	my $svframe = shift;
	my $sth = $dbh->prepare("UPDATE `registryTransaction`.`transaction_identifier` SET `cmd` = ?, `obj_type` = ?, `obj_id` = ?, `code` = ?, `msg` = ?, `svTRID` = ?, `svTRIDframe` = ?, `svdate` = ?, `svmicrosecond` = ? WHERE `id` = ?") or die $dbh->errstr;
	my $date_for_sv_transaction = microsecond();
	my ($svdate,$svmicrosecond) = split(/\./, $date_for_sv_transaction);
	$sth->execute($blob->{cmd},$blob->{obj_type},$blob->{obj_id},$blob->{resultCode},$blob->{human_readable_message},$blob->{svTRID},$svframe,$svdate,$svmicrosecond,$transaction_id) or die $sth->errstr;
	return 1;
}