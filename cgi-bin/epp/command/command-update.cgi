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
	$xp->set_namespace('rgp', 'urn:ietf:params:xml:ns:rgp-1.0');
	$xp->set_namespace('identExt', 'http://www.nic.xx/XXNIC-EPP/identExt-1.0');

my $blob = {};
$blob->{clTRID} = $cltrid;
$blob->{resultCode} = 1000;
$blob->{cmd} = 'update';

my $update_node = $xp->findnodes('/epp:epp/epp:command/epp:update')->get_node(0);
	my $extension_node = $xp->findnodes('/epp:epp/epp:command/epp:extension')->get_node(0);
my ($registrar_id) = $dbh->selectrow_array("SELECT `id` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

my $obj;
	my $obj_ext;
if ($obj = $xp->find('contact:update',$update_node)->get_node(0)) {
	################################################################
	#
	#			<update><contact:id>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-contact:update';
	$blob->{command} = 'update_contact';
	$blob->{obj_type} = 'contact';

	# -  A <contact:id> element that contains the server-unique identifier of the contact object to be updated.
	my $identifier = $xp->findvalue('contact:id[1]', $obj);
	$blob->{obj_id} = $identifier;

	# EPP commands are atomic, so a command will either succeed completely or fail completely. Success and failure results MUST NOT be mixed.

	my $contact_rem = $xp->find('contact:rem', $obj)->get_node(0);
	my $contact_add = $xp->find('contact:add', $obj)->get_node(0);
	my $contact_chg = $xp->find('contact:chg', $obj)->get_node(0);
	my $identExt_update;
	if ($extension_node) {
		$identExt_update = $xp->find('identExt:update',$extension_node)->get_node(0);
	}

	if (!($contact_rem && $xp->find('./*', $contact_rem)->size > 0) && !($contact_add && $xp->find('./*', $contact_add)->size > 0) && !($contact_chg && $xp->find('./*', $contact_chg)->size > 0) && !($extension_node && $xp->find('./*', $extension_node)->size > 0)) {
		$blob->{resultCode} = 2003; # Required parameter missing. At least one <contact:add>, <contact:rem>, or <contact:chg> element MUST be provided if the command is not being extended.
		$blob->{human_readable_message} = 'At least one contact:rem || contact:add || contact:chg';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if (!$identifier) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Nu este identifier';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$identifier = uc($identifier);
	my ($contact_id,$registrar_id_contact) = $dbh->selectrow_array("SELECT `id`,`clid` FROM `contact` WHERE `identifier` = '$identifier' LIMIT 1");
	if (!$contact_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'Nu este contact id';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ($registrar_id != $registrar_id_contact) {
		$blob->{resultCode} = 2201; # Authorization error
		$blob->{human_readable_message} = 'Apartine altui registrar';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my $sth = $dbh->prepare("SELECT `status` FROM `contact_status` WHERE `contact_id` = ?") or die $dbh->errstr;
	$sth->execute($contact_id) or die $sth->errstr;
	while (my ($status) = $sth->fetchrow_array()) {
		if (($status =~ m/.*(serverUpdateProhibited)$/) || ($status =~ /^pending/)) {
			$blob->{resultCode} = 2304; # Object status prohibits operation
			$blob->{human_readable_message} = 'Are un status serverUpdateProhibited sau pendingUpdate care nu permite modificarea, mai intii schimba statutul apoi faci update, de mai studiat interpretarile EPP 5730 aici';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	$sth->finish;

	# verificam daca are restrictii la update, daca da apoi mai jos verificam daca o venit rem la acest status, daca nu exista rem, apoi returnam error
	my $clientUpdateProhibited = 0;
	($clientUpdateProhibited) = $dbh->selectrow_array("SELECT `id` FROM `contact_status` WHERE `contact_id` = '$contact_id' AND `status` = 'clientUpdateProhibited' LIMIT 1");

	# mai intii verificam tot ce intra, daca totul este conform RFC si conform policy, ap doar atunci facem update
	#_________________________________________________________________________________________________________________
	if ($contact_rem && $xp->find('./*', $contact_rem)->size > 0) {
		my $status_list = $xp->find('contact:status/@s', $contact_rem);

		if ($status_list->size == 0) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'At least one status element MUST be present';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			if ($status eq 'clientUpdateProhibited') {
				$clientUpdateProhibited = 0;
			}
			if ($status !~ /^(clientDeleteProhibited|clientTransferProhibited|clientUpdateProhibited)$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Sunt acceptate doar aceste status-uri clientDeleteProhibited|clientTransferProhibited|clientUpdateProhibited';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
	}

	if ($clientUpdateProhibited) {
		$blob->{resultCode} = 2304; # Object status prohibits operation
		$blob->{human_readable_message} = 'Are status clientUpdateProhibited dar tu nu ai indicat acest status la stergere';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}
	#_________________________________________________________________________________________________________________
	if ($contact_add && $xp->find('./*', $contact_add)->size > 0) {
		my $status_list = $xp->find('contact:status/@s', $contact_add);

		if ($status_list->size == 0) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'At least one status element MUST be present';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			if ($status !~ /^(clientDeleteProhibited|clientTransferProhibited|clientUpdateProhibited)$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Sunt acceptate doar aceste status-uri clientDeleteProhibited|clientTransferProhibited|clientUpdateProhibited';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}

			if ($xp->find('contact:status[@s="'.$status.'"]', $contact_rem)->size == 0) {
				my ($contact_status_id) = $dbh->selectrow_array("SELECT `id` FROM `contact_status` WHERE `contact_id` = '$contact_id' AND `status` = '$status' LIMIT 1");
				if ($contact_status_id) {
					$blob->{resultCode} = 2306; # Parameter value policy error
					$blob->{human_readable_message} = "This status '$status' already exists for this contact";
						$blob->{optionalValue} = 1;
						$blob->{xmlns_obj} = 'xmlns:contact';
						$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
						$blob->{obj_elem} = 'contact:status';
						$blob->{obj_elem_value} = $status;
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
			}
		}
	}
	#_________________________________________________________________________________________________________________
	if ($contact_chg && $xp->find('./*', $contact_chg)->size > 0) {
		if (!defined $contact_chg->getFirstChild) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'At least one child element MUST be present';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		my $postalInfo_int = $xp->find('contact:postalInfo[@type=\'int\']', $contact_chg)->get_node(0);
		# A <contact:name> element that contains the name of the individual or role represented by the contact.
		my $postalInfo_int_name = $xp->findvalue('contact:name[1]', $postalInfo_int);
		my $postalInfo_int_org = $xp->findvalue('contact:org[1]', $postalInfo_int);
		my $postalInfo_int_addr = $xp->find('contact:addr', $postalInfo_int)->get_node(0);
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
			if ($postalInfo_int_name) {
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

			if ($postalInfo_int_addr) {
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

			if ($postalInfo_int_addr) {
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
		}



		my $postalInfo_loc = $xp->find('contact:postalInfo[@type=\'loc\']', $contact_chg)->get_node(0);
		# A <contact:name> element that contains the name of the individual or role represented by the contact.
		my $postalInfo_loc_name = $xp->findvalue('contact:name[1]', $postalInfo_loc);
		my $postalInfo_loc_org = $xp->findvalue('contact:org[1]', $postalInfo_loc);
		my $postalInfo_loc_addr = $xp->find('contact:addr', $postalInfo_loc)->get_node(0);
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
			if ($postalInfo_loc_name) {
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

			if ($postalInfo_loc_addr) {
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

			if ($postalInfo_loc_addr) {
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
		}







		# An OPTIONAL <contact:voice> element that contains the contact's voice telephone number.
		my $voice = $xp->findvalue('contact:voice[1]', $contact_chg);
		my $voice_x = $xp->findvalue('contact:voice/@x[1]', $contact_chg);
		if ($voice && ($voice !~ /^\+\d{1,3}\.\d{1,14}$/ || length($voice) > 17)) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Voice (\+[0-9]{1,3}\.[0-9]{1,14})';
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
		my $fax = $xp->findvalue('contact:fax[1]', $contact_chg);
		my $fax_x = $xp->findvalue('contact:fax/@x[1]', $contact_chg);
		if ($fax && ($fax !~ /^\+\d{1,3}\.\d{1,14}$/ || length($fax) > 17)) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Fax (\+[0-9]{1,3}\.[0-9]{1,14})';
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
		my $email = $xp->findvalue('contact:email[1]', $contact_chg);
		if ($email) {
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
		}

		# A <contact:authInfo> element that contains authorization information associated with the contact object.
		my $authInfo_pw = $xp->findvalue('contact:authInfo/contact:pw[1]', $contact_chg);
		if ($authInfo_pw) {
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

#			if ($authInfo_pw !~ /[a-z]/) {
#				$blob->{resultCode} = 2005; # Parameter value syntax error
#				$blob->{human_readable_message} = 'Password should have both upper and lower case characters';
#					$blob->{optionalValue} = 1;
#					$blob->{xmlns_obj} = 'xmlns:contact';
#					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
#					$blob->{obj_elem} = 'contact:authInfo';
#					$blob->{obj_elem_value} = $authInfo_pw;
#				my $msg = epp_writer($blob);
#				print $msg;
#				my $uptr = update_transaction($msg);
#				exit;
#			}

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
		}
	}
	#_________________________________________________________________________________________________________________
	my $nin = $xp->findvalue('identExt:nin[1]', $identExt_update)->value; # 1-16
	my $nin_type = $xp->findvalue('identExt:nin/@type[1]', $identExt_update); # personal|business
	if ($identExt_update) {
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



	
	# aici facem update deja
	#_________________________________________________________________________________________________________________
	if ($contact_rem && $xp->find('./*', $contact_rem)->size > 0) {
		my $status_list = $xp->find('contact:status/@s', $contact_rem);

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			my $sth = $dbh->prepare("DELETE FROM `contact_status` WHERE `contact_id` = ? AND `status` = ?") or die $dbh->errstr;
			$sth->execute($contact_id,$status) or die $sth->errstr;
		}
	}

	#_________________________________________________________________________________________________________________
	if ($contact_add && $xp->find('./*', $contact_add)->size > 0) {
		my $status_list = $xp->find('contact:status/@s', $contact_add);

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			# aici de revizuit daca el da la inserare acelas status care exista va fi un internal error
			# de scos eroarea in exterior
			my $sth = $dbh->prepare("INSERT INTO `contact_status` (`contact_id`,`status`) VALUES(?,?)") or die $dbh->errstr;
			$sth->execute($contact_id,$status) or die $sth->errstr;
		}
	}

	#_________________________________________________________________________________________________________________
	if ($contact_chg && $xp->find('./*', $contact_chg)->size > 0) {
		my ($e_voice,$e_voice_x,$e_fax,$e_fax_x,$e_email,$e_clid,$e_crid,$e_crdate,$e_upid,$e_update,$e_trdate,$e_trstatus,$e_reid,$e_redate,$e_acid,$e_acdate,$e_disclose_voice,$e_disclose_fax,$e_disclose_email) = $dbh->selectrow_array("SELECT `voice`,`voice_x`,`fax`,`fax_x`,`email`,`clid`,`crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`disclose_voice`,`disclose_fax`,`disclose_email` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");

		my ($int_name,$int_org,$int_street1,$int_street2,$int_street3,$int_city,$int_sp,$int_pc,$int_cc,$disclose_name_int,$disclose_org_int,$disclose_addr_int) = $dbh->selectrow_array("SELECT `name`,`org`,`street1`,`street2`,`street3`,`city`,`sp`,`pc`,`cc`,`disclose_name_int`,`disclose_org_int`,`disclose_addr_int` FROM `contact_postalInfo` WHERE `contact_id` = '$contact_id' AND `type` = 'int' LIMIT 1");
		my ($loc_name,$loc_org,$loc_street1,$loc_street2,$loc_street3,$loc_city,$loc_sp,$loc_pc,$loc_cc,$disclose_name_loc,$disclose_org_loc,$disclose_addr_loc) = $dbh->selectrow_array("SELECT `name`,`org`,`street1`,`street2`,`street3`,`city`,`sp`,`pc`,`cc`,`disclose_name_loc`,`disclose_org_loc`,`disclose_addr_loc` FROM `contact_postalInfo` WHERE `contact_id` = '$contact_id' AND `type` = 'loc' LIMIT 1");

		my ($e_authInfo_pw) = $dbh->selectrow_array("SELECT `authinfo` FROM `contact_authInfo` WHERE `contact_id` = '$contact_id' AND `authtype` = 'pw' LIMIT 1");
		my ($e_authInfo_ext) = $dbh->selectrow_array("SELECT `authinfo` FROM `contact_authInfo` WHERE `contact_id` = '$contact_id' AND `authtype` = 'ext' LIMIT 1");

		my $postalInfo_int = $xp->find('contact:postalInfo[@type=\'int\']', $contact_chg)->get_node(0);
		if ($postalInfo_int) {
			my $postalInfo_int_name = $xp->find('contact:name', $postalInfo_int);
			$int_name = $postalInfo_int_name->get_node(0)->string_value if ($postalInfo_int_name->size);

			my $postalInfo_int_org = $xp->find('contact:org', $postalInfo_int);
			$int_org = $postalInfo_int_org->get_node(0)->string_value if ($postalInfo_int_org->size);

			my $postalInfo_int_street_list = $xp->find('contact:addr/contact:street', $postalInfo_int);
			if ($postalInfo_int_street_list->size) {
				my @street_int;
				foreach my $node_int ($postalInfo_int_street_list->get_nodelist) {
					push(@street_int, $node_int->string_value);
				}
				$int_street1 = $street_int[0];
				$int_street2 = $street_int[1] || '';
				$int_street3 = $street_int[2] || '';
			}

			my $postalInfo_int_city = $xp->find('contact:addr/contact:city', $postalInfo_int);
			$int_city = $postalInfo_int_city->get_node(0)->string_value if ($postalInfo_int_city->size);

			my $postalInfo_int_sp = $xp->find('contact:addr/contact:sp', $postalInfo_int);
			$int_sp = '';
			$int_sp = $postalInfo_int_sp->get_node(0)->string_value if ($postalInfo_int_sp->size);

			my $postalInfo_int_pc = $xp->find('contact:addr/contact:pc', $postalInfo_int);
			$int_pc = '';
			$int_pc = $postalInfo_int_pc->get_node(0)->string_value if ($postalInfo_int_pc->size);

			my $postalInfo_int_cc = $xp->find('contact:addr/contact:cc', $postalInfo_int);
			$int_cc = $postalInfo_int_cc->get_node(0)->string_value if ($postalInfo_int_cc->size);
		}



		my $postalInfo_loc = $xp->find('contact:postalInfo[@type=\'loc\']', $contact_chg)->get_node(0);
		if ($postalInfo_loc) {
			my $postalInfo_loc_name = $xp->find('contact:name', $postalInfo_loc);
			$loc_name = $postalInfo_loc_name->get_node(0)->string_value if ($postalInfo_loc_name->size);

			my $postalInfo_loc_org = $xp->find('contact:org', $postalInfo_loc);
			$loc_org = $postalInfo_loc_org->get_node(0)->string_value if ($postalInfo_loc_org->size);

			my $postalInfo_loc_street_list = $xp->find('contact:addr/contact:street', $postalInfo_loc);
			if ($postalInfo_loc_street_list->size) {
				my @street_loc;
				foreach my $node_loc ($postalInfo_loc_street_list->get_nodelist) {
					push(@street_loc, $node_loc->string_value);
				}
				$loc_street1 = $street_loc[0];
				$loc_street2 = $street_loc[1] || '';
				$loc_street3 = $street_loc[2] || '';
			}

			my $postalInfo_loc_city = $xp->find('contact:addr/contact:city', $postalInfo_loc);
			$loc_city = $postalInfo_loc_city->get_node(0)->string_value if ($postalInfo_loc_city->size);

			my $postalInfo_loc_sp = $xp->find('contact:addr/contact:sp', $postalInfo_loc);
			$loc_sp = '';
			$loc_sp = $postalInfo_loc_sp->get_node(0)->string_value if ($postalInfo_loc_sp->size);

			my $postalInfo_loc_pc = $xp->find('contact:addr/contact:pc', $postalInfo_loc);
			$loc_pc = '';
			$loc_pc = $postalInfo_loc_pc->get_node(0)->string_value if ($postalInfo_loc_pc->size);

			my $postalInfo_loc_cc = $xp->find('contact:addr/contact:cc', $postalInfo_loc);
			$loc_cc = $postalInfo_loc_cc->get_node(0)->string_value if ($postalInfo_loc_cc->size);
		}



		my $voice = $xp->find('contact:voice', $contact_chg);
		if ($voice->size) {
			$e_voice = $voice->get_node(0)->string_value;
			my $voice_x = $xp->find('contact:voice/@x', $contact_chg);
			$e_voice_x = ($voice_x->size) ? $voice_x->get_node(0)->string_value : '';
		}

		my $fax = $xp->find('contact:fax', $contact_chg);
		if ($fax->size) {
			$e_fax = $fax->get_node(0)->string_value;
			my $fax_x = $xp->find('contact:fax/@x', $contact_chg);
			$e_fax_x = ($fax_x->size) ? $fax_x->get_node(0)->string_value : '';
		}

		my $email = $xp->find('contact:email', $contact_chg);
		$e_email = $email->get_node(0)->string_value if ($email->size);

		my $authInfo_pw = $xp->find('contact:authInfo/contact:pw', $contact_chg);
		$e_authInfo_pw = $authInfo_pw->get_node(0)->string_value if ($authInfo_pw->size);

		my $authInfo_ext = $xp->find('contact:authInfo/contact:ext', $contact_chg);
		$e_authInfo_ext = $authInfo_ext->get_node(0)->string_value if ($authInfo_ext->size);


		my $sth = $dbh->prepare("UPDATE `contact` SET `voice` = ?, `voice_x` = ?, `fax` = ?, `fax_x` = ?, `email` = ?, `update` = CURRENT_TIMESTAMP WHERE `id` = ?") or die $dbh->errstr;
		$sth->execute($e_voice || undef,$e_voice_x || undef,$e_fax || undef,$e_fax_x || undef,$e_email,$contact_id) or die $sth->errstr;

		$sth = $dbh->prepare("UPDATE `contact_postalInfo` SET `name` = ?, `org` = ?, `street1` = ?, `street2` = ?, `street3` = ?, `city` = ?, `sp` = ?, `pc` = ?, `cc` = ? WHERE `contact_id` = ? AND `type` = ?") or die $dbh->errstr;
		$sth->execute($int_name,$int_org,$int_street1,$int_street2,$int_street3,$int_city,$int_sp,$int_pc,$int_cc,$contact_id,'int') or die $sth->errstr;

		$sth = $dbh->prepare("UPDATE `contact_postalInfo` SET `name` = ?, `org` = ?, `street1` = ?, `street2` = ?, `street3` = ?, `city` = ?, `sp` = ?, `pc` = ?, `cc` = ? WHERE `contact_id` = ? AND `type` = ?") or die $dbh->errstr;
		$sth->execute($loc_name,$loc_org,$loc_street1,$loc_street2,$loc_street3,$loc_city,$loc_sp,$loc_pc,$loc_cc,$contact_id,'loc') or die $sth->errstr;

		$sth = $dbh->prepare("UPDATE `contact_authInfo` SET `authinfo` = ? WHERE `contact_id` = ? AND `authtype` = ?") or die $dbh->errstr;
		$sth->execute($e_authInfo_pw,$contact_id,'pw') or die $sth->errstr;

		$sth = $dbh->prepare("UPDATE `contact_authInfo` SET `authinfo` = ? WHERE `contact_id` = ? AND `authtype` = ?") or die $dbh->errstr;
		$sth->execute($e_authInfo_ext,$contact_id,'ext') or die $sth->errstr;
	}
	#_________________________________________________________________________________________________________________
	if ($identExt_update) {
		my $sth = $dbh->prepare("UPDATE `contact` SET `nin` = ?, `nin_type` = ?, `update` = CURRENT_TIMESTAMP WHERE `id` = ?") or die $dbh->errstr;
		$sth->execute($nin || undef,$nin_type || undef,$contact_id) or die $sth->errstr;
	}

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('domain:update',$update_node)->get_node(0)) {
	################################################################
	#
	#			<update><domain:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-domain:update';
	$blob->{command} = 'update_domain';
	$blob->{obj_type} = 'domain';

	# -  A <domain:name> element that contains the fully qualified name of the domain object to be updated.
	my $name = $xp->findvalue('domain:name[1]', $obj);
	$blob->{obj_id} = $name;

	my $domain_rem = $xp->find('domain:rem', $obj)->get_node(0);
	my $domain_add = $xp->find('domain:add', $obj)->get_node(0);
	my $domain_chg = $xp->find('domain:chg', $obj)->get_node(0);
	my $rgp_update;
	if ($extension_node) {
		$rgp_update = $xp->find('rgp:update',$extension_node)->get_node(0);
	}

	if (!($domain_rem && $xp->find('./*', $domain_rem)->size > 0) && !($domain_add && $xp->find('./*', $domain_add)->size > 0) && !($domain_chg && $xp->find('./*', $domain_chg)->size > 0) && !($extension_node && $xp->find('./*', $extension_node)->size > 0)) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'At least one domain:rem || domain:add || domain:chg';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if (!$name) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Nu este indicat name';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$name = uc($name);
	my ($domain_id,$tldid,$exdate,$registrar_id_domain) = $dbh->selectrow_array("SELECT `id`,`tldid`,`exdate`,`clid` FROM `domain` WHERE `name` = '$name' LIMIT 1");
	if (!$domain_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'Nu exista asa domeniu in registry';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ($registrar_id != $registrar_id_domain) {
		$blob->{resultCode} = 2201; # Authorization error
		$blob->{human_readable_message} = 'Nu ai privilegii sa modifici un nume de domeniu care apartine altui registrar';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my $sth = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
	$sth->execute($domain_id) or die $sth->errstr;
	while (my ($status) = $sth->fetchrow_array()) {
		if (($status =~ m/.*(serverUpdateProhibited)$/) || ($status =~ /^pendingTransfer/)) {
			$blob->{resultCode} = 2304; # Object status prohibits operation
			$blob->{human_readable_message} = 'Are un status serverUpdateProhibited sau pendingUpdate care nu permite modificarea, mai intii schimba statutul apoi faci update, de mai studiat interpretarile EPP 5730 aici';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}

	# verificam daca are restrictii la update, daca da apoi mai jos verificam daca o venit rem la acest status, daca nu exista rem, apoi returnam error
	my $clientUpdateProhibited = 0;
	($clientUpdateProhibited) = $dbh->selectrow_array("SELECT `id` FROM `domain_status` WHERE `domain_id` = '$domain_id' AND `status` = 'clientUpdateProhibited' LIMIT 1");

	# mai intii verificam tot ce intra, daca totul este conform RFC si conform policy, ap doar atunci facem update
	#_________________________________________________________________________________________________________________
	if ($domain_rem && $xp->find('./*', $domain_rem)->size > 0) {
		my $ns = $xp->find('domain:ns', $domain_rem)->get_node(0); # An OPTIONAL
		my $contact_list = $xp->find('domain:contact', $domain_rem); # Zero or more
		my $status_list = $xp->find('domain:status/@s', $domain_rem); # Zero or more

		if (!$ns && $contact_list->size == 0 && $status_list->size == 0) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'At least one element MUST be present';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			if ($status eq 'clientUpdateProhibited') {
				$clientUpdateProhibited = 0;
			}
			if ($status !~ /^(clientDeleteProhibited|clientHold|clientRenewProhibited|clientTransferProhibited|clientUpdateProhibited)$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Sunt acceptate doar aceste status-uri clientDeleteProhibited|clientTransferProhibited|clientUpdateProhibited';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
	}

	if ($clientUpdateProhibited) {
		# a ramas de verificat aici
		$blob->{resultCode} = 2304; # Object status prohibits operation
		$blob->{human_readable_message} = 'Are status clientUpdateProhibited dar tu nu ai indicat acest status la stergere';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}
	#_________________________________________________________________________________________________________________
	if ($domain_add && $xp->find('./*', $domain_add)->size > 0) {
		my $ns = $xp->find('domain:ns', $domain_add)->get_node(0); # An OPTIONAL
		my $hostObj_list = $xp->find('domain:hostObj', $ns);
		my $hostAttr_list = $xp->find('domain:hostAttr', $ns);
		my $contact_list = $xp->find('domain:contact', $domain_add); # Zero or more
		my $status_list = $xp->find('domain:status/@s', $domain_add); # Zero or more

		if (!$ns && $contact_list->size == 0 && $status_list->size == 0 && $hostObj_list->size == 0 && $hostAttr_list->size == 0) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'At least one element MUST be present';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			if ($status !~ /^(clientDeleteProhibited|clientHold|clientRenewProhibited|clientTransferProhibited|clientUpdateProhibited)$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Sunt acceptate doar aceste status-uri clientDeleteProhibited|clientTransferProhibited|clientUpdateProhibited';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}

			if ($xp->find('domain:status[@s="'.$status.'"]', $domain_rem)->size == 0) {
				my ($domain_status_id) = $dbh->selectrow_array("SELECT `id` FROM `domain_status` WHERE `domain_id` = '$domain_id' AND `status` = '$status' LIMIT 1");
				if ($domain_status_id) {
					$blob->{resultCode} = 2306; # Parameter value policy error
					$blob->{human_readable_message} = "This status '$status' already exists for this domain";
						$blob->{optionalValue} = 1;
						$blob->{xmlns_obj} = 'xmlns:domain';
						$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
						$blob->{obj_elem} = 'domain:status';
						$blob->{obj_elem_value} = $status;
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
			}
		}

		if (($hostObj_list->size() > 0) && ($hostAttr_list->size() > 0)) {
			$blob->{resultCode} = 2001; # Command syntax error
			$blob->{human_readable_message} = 'Nu poate fi in acelas timp hostObj si hostAttr, ori una ori alta';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($hostObj_list->size() > 13) {
			$blob->{resultCode} = 2306; # Parameter value policy error
			$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu sunt permise mai mult de 13 domain:hostObj, deoarece RFC5730 nu impune limita';
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
			$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu sunt permise mai mult de 13 domain:hostAttr, deoarece RFC5730 nu impune limita';
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
					$blob->{resultCode} = 2306; # Parameter value policy error
					$blob->{human_readable_message} = "Duplicate NAMESERVER ($hostObj)";
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
					$blob->{resultCode} = 2306; # Parameter value policy error
					$blob->{human_readable_message} = "Duplicate NAMESERVER ($hostName)";
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
					# facem o verificare, daca acest hostObj are TLD din acest registry, daca asa domeniu nu exista inregistrat si e diferit decit cel ce se vrea inregistrat acuma, dam eroare
					# selectam din cimpul tld, le facem cu litere mari apoi le comparam
					my $host_from_this_registry = 0;
					my $sth = $dbh->prepare("SELECT `tld` FROM `domain_tld`") or die $dbh->errstr;
					$sth->execute() or die $sth->errstr;
					while (my ($tld) = $sth->fetchrow_array()) {
						$tld = uc($tld);
						$tld =~ s/\./\\./g;
						if ($hostObj =~ /$tld$/i) {
							$host_from_this_registry = 1;
							last;
						}
					}
					$sth->finish;

					if ($host_from_this_registry) {
						if ($hostObj =~ /\.$name$/i) {
							my $superordinate_domain = 1;
						}
						else {
							my ($host_id_already_exist) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$hostObj' LIMIT 1");
							if (!$host_id_already_exist) {
								$blob->{resultCode} = 2303; # Object does not exist
								$blob->{human_readable_message} = "Invalid domain:hostObj $hostObj";
								my $msg = epp_writer($blob);
								print $msg;
								my $uptr = update_transaction($msg);
								exit;
							}
						}
					}
				}
				else {
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

				if ($hostName =~ /\.$name$/i) {
					my $hostAddr_list = $xp->find('domain:hostAddr', $node);
					# aici facem o verificare daca un host are mai mult de 13 adrese IP apoi reject
					# Max 13 IP per host.
					if ($hostAddr_list->size() > 13) {
						$blob->{resultCode} = 2306; # Parameter value policy error
						$blob->{human_readable_message} = 'Vom specifica in Rules & Policies for EPP ca nu sunt permise mai mult de 13 IP per host deoarece RFC5730 nu impune limita';
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
								$blob->{resultCode} = 2306; # Parameter value policy error
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

					foreach my $node ($hostAddr_list->get_nodelist) {
						my $hostAddr = $node->string_value;
						my $addr_type = $node->findvalue('@ip[1]') || 'v4';
						if ($addr_type eq 'v6') {
							if ($hostAddr =~ m/^[\da-fA-F]{1,4}(:[\da-fA-F]{1,4}){7}$/ || $hostAddr =~ m/^::$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){1,7}:$/ || $hostAddr =~ m/^[\da-fA-F]{1,4}:(:[\da-fA-F]{1,4}){1,6}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){2}(:[\da-fA-F]{1,4}){1,5}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){3}(:[\da-fA-F]{1,4}){1,4}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){4}(:[\da-fA-F]{1,4}){1,3}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){5}(:[\da-fA-F]{1,4}){1,2}$/ || $hostAddr =~ m/^([\da-fA-F]{1,4}:){6}:[\da-fA-F]{1,4}$/) {
								# true
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
							# Also note that the EPP registry may prohibit certain IP ranges from being used.
							if ($hostAddr =~ m/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/ && $a < 256 &&  $b < 256 && $c < 256 && $d < 256) {
								# true
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
					$blob->{resultCode} = 2005; # Parameter value syntax error
					$blob->{human_readable_message} = "Invalid domain:hostName $hostName";
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

		foreach my $node ($contact_list->get_nodelist) {
			my $contact = $node->string_value;
			my $contact_type = $node->findvalue('@type[1]');
			$contact = uc($contact);
			my ($contact_id) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$contact' LIMIT 1");
			if (!$contact_id) {
				$blob->{resultCode} = 2303; # Object does not exist
				$blob->{human_readable_message} = "This contact '$contact' does not exist";
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}

			my ($domain_contact_map_id) = $dbh->selectrow_array("SELECT `id` FROM `domain_contact_map` WHERE `domain_id` = '$domain_id' AND `contact_id` = '$contact_id' AND `type` = '$contact_type' LIMIT 1");
			if ($domain_contact_map_id) {
				$blob->{resultCode} = 2306; # Parameter value policy error
				$blob->{human_readable_message} = "This contact '$contact' already exists for type '$contact_type'";
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:domain';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
					$blob->{obj_elem} = 'domain:contact';
					$blob->{obj_elem_value} = $contact;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
	}
	#_________________________________________________________________________________________________________________
	if ($domain_chg && $xp->find('./*', $domain_chg)->size > 0) {
		my $registrant = $xp->findvalue('domain:registrant[1]', $domain_chg); # element that contains the identifier

		$registrant = uc($registrant);
		if ($registrant) {
			my ($registrant_id) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$registrant' LIMIT 1");
			# This object identifier MUST be known to the server before the contact object can be associated with the domain object.
			# An empty element can be used to remove registrant information.
			if (!$registrant_id) {
				$blob->{resultCode} = 2303; # Object does not exist
				$blob->{human_readable_message} = 'Nu exista asa registrant This object identifier MUST be known to the server before the contact object can be associated with the domain object';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		my $sth = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
		$sth->execute($domain_id) or die $sth->errstr;
		while (my ($status) = $sth->fetchrow_array()) {
			if (($status =~ m/.*(serverUpdateProhibited)$/) || ($status =~ /^pendingTransfer/)) {
				# This response code MUST be returned when a server receives a command to transform an object that cannot be completed due to server policy or business practices.
				$blob->{resultCode} = 2304; # Object status prohibits operation
				$blob->{human_readable_message} = 'Are un status care nu permite modificarea, mai intii schimba statutul apoi faci update, de mai studiat interpretarile EPP 5730 aici';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
		$sth->finish;

		my $authInfo_pw = $xp->findvalue('domain:authInfo/domain:pw[1]', $domain_chg); # element that contains authorization
		if ($authInfo_pw) {
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

#			if ($authInfo_pw !~ /[a-z]/) {
#				$blob->{resultCode} = 2005; # Parameter value syntax error
#				$blob->{human_readable_message} = 'Password should have both upper and lower case characters';
#					$blob->{optionalValue} = 1;
#					$blob->{xmlns_obj} = 'xmlns:domain';
#					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
#					$blob->{obj_elem} = 'domain:authInfo';
#					$blob->{obj_elem_value} = $authInfo_pw;
#				my $msg = epp_writer($blob);
#				print $msg;
#				my $uptr = update_transaction($msg);
#				exit;
#			}

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
		}
	}
	#_________________________________________________________________________________________________________________
	if ($rgp_update) {
		my $op_attribute = $xp->findvalue('rgp:restore/@op[1]', $rgp_update); # request|report

		if ($op_attribute eq 'request') {
			my $temp_id_rgpstatus = $dbh->selectrow_array("SELECT COUNT(`id`) AS `ids` FROM `domain` WHERE `rgpstatus` = 'redemptionPeriod' AND `id` = '$domain_id' LIMIT 1");
			if ($temp_id_rgpstatus == 0) {
				$blob->{resultCode} = 2304; # Object status prohibits operation
				$blob->{human_readable_message} = 'pendingRestore se poate de facut doar daca domeniul este acuma in redemptionPeriod rgpStatus';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			my $temp_id_status = $dbh->selectrow_array("SELECT COUNT(`id`) AS `ids` FROM `domain_status` WHERE `status` = 'pendingDelete' AND `domain_id` = '$domain_id' LIMIT 1");
			if ($temp_id_status == 0) {
				$blob->{resultCode} = 2304; # Object status prohibits operation
				$blob->{human_readable_message} = 'pendingRestore se poate de facut doar daca domeniul este acuma in pendingDelete status';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
		elsif ($op_attribute eq 'report') {
			my $temp_id = $dbh->selectrow_array("SELECT COUNT(`id`) AS `ids` FROM `domain` WHERE `rgpstatus` = 'pendingRestore' AND `id` = '$domain_id' LIMIT 1");
			if ($temp_id == 0) {
				$blob->{resultCode} = 2304; # Object status prohibits operation
				$blob->{human_readable_message} = 'report se poate de transmis doar daca domeniul este in pendingRestore status';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
	}





	# aici facem update deja
	#_________________________________________________________________________________________________________________
	if ($domain_rem && $xp->find('./*', $domain_rem)->size > 0) {
		my $ns = $xp->find('domain:ns', $domain_rem)->get_node(0); # An OPTIONAL
		my $contact_list = $xp->find('domain:contact', $domain_rem); # Zero or more
		my $status_list = $xp->find('domain:status/@s', $domain_rem); # Zero or more

		my $hostObj_list = $xp->find('domain:hostObj', $ns);
		my $hostAttr_list = $xp->find('domain:hostAttr', $ns);

		foreach my $node ($hostObj_list->get_nodelist) {
			my $hostObj = $node->string_value;
			$hostObj = uc($hostObj);
			my ($host_id) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$hostObj' LIMIT 1");
			if ($host_id) {
				my $sth = $dbh->prepare("DELETE FROM `domain_host_map` WHERE `domain_id` = ? AND `host_id` = ?") or die $dbh->errstr;
				$sth->execute($domain_id,$host_id) or die $sth->errstr;
			}
		}

		foreach my $node ($hostAttr_list->get_nodelist) {
			my $hostName = $xp->findvalue('domain:hostName[1]', $node);
			$hostName = uc($hostName);
			my ($host_id) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$hostName' LIMIT 1");
			if ($host_id) {
				my $sth = $dbh->prepare("DELETE FROM `domain_host_map` WHERE `domain_id` = ? AND `host_id` = ?") or die $dbh->errstr;
				$sth->execute($domain_id,$host_id) or die $sth->errstr;

				$sth = $dbh->prepare("DELETE FROM `host_addr` WHERE `host_id` = ?") or die $dbh->errstr;
				$sth->execute($host_id) or die $sth->errstr;

				$sth = $dbh->prepare("DELETE FROM `host` WHERE `host_id` = ?") or die $dbh->errstr;
				$sth->execute($host_id) or die $sth->errstr;
			}
		}

		foreach my $node ($contact_list->get_nodelist) {
			my $contact = $node->string_value;
			my $contact_type = $node->findvalue('@type[1]');

			$contact = uc($contact);
			my ($contact_id) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$contact' LIMIT 1");
			if ($contact_id) {
				my $sth = $dbh->prepare("DELETE FROM `domain_contact_map` WHERE `domain_id` = ? AND `contact_id` = ? AND `type` = ?") or die $dbh->errstr;
				$sth->execute($domain_id,$contact_id,$contact_type) or die $sth->errstr;
			}
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			my $sth = $dbh->prepare("DELETE FROM `domain_status` WHERE `domain_id` = ? AND `status` = ?") or die $dbh->errstr;
			$sth->execute($domain_id,$status) or die $sth->errstr;
		}
	}

	#_________________________________________________________________________________________________________________
	if ($domain_add && $xp->find('./*', $domain_add)->size > 0) {
		my $ns = $xp->find('domain:ns', $domain_add)->get_node(0); # An OPTIONAL
		my $hostObj_list = $xp->find('domain:hostObj', $ns);
		my $hostAttr_list = $xp->find('domain:hostAttr', $ns);
		my $contact_list = $xp->find('domain:contact', $domain_add); # Zero or more
		my $status_list = $xp->find('domain:status/@s', $domain_add); # Zero or more

		foreach my $node ($hostObj_list->get_nodelist) {
			my $hostObj = $node->string_value;
			# A host object MUST be known to the server before the host object can be associated with a domain object.
			my ($hostObj_already_exist) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$hostObj' LIMIT 1");
			if ($hostObj_already_exist) {
				my ($domain_host_map_id) = $dbh->selectrow_array("SELECT `domain_id` FROM `domain_host_map` WHERE `domain_id` = '$domain_id' AND `host_id` = '$hostObj_already_exist' LIMIT 1");
				if (!$domain_host_map_id) {
					$dbh->do("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES('$domain_id','$hostObj_already_exist')") or die $dbh->errstr;
				}
				else {
					# cred ca el aici o indicat ceva care se dubleaza, mai rare cazuri dar totusi
					$dbh->do("INSERT INTO `error_log` (`registrar_id`,`log`,`date`) VALUES('$registrar_id','Domain : $name ;   hostObj : $hostObj - se dubleaza',CURRENT_TIMESTAMP)") or die $dbh->errstr;
				}
			}
			else {
				# facem o verificare, daca acest hostObj are TLD din acest registry, daca asa domeniu nu exista inregistrat si e diferit decit cel ce se vrea inregistrat acuma, dam eroare
				# selectam din cimpul tld, le facem cu litere mari apoi le comparam
				my $host_from_this_registry = 0;
				my $sth = $dbh->prepare("SELECT `tld` FROM `domain_tld`") or die $dbh->errstr;
				$sth->execute() or die $sth->errstr;
				while (my ($tld) = $sth->fetchrow_array()) {
					$tld = uc($tld);
					$tld =~ s/\./\\./g;
					if ($hostObj =~ /$tld$/i) {
						$host_from_this_registry = 1;
						last;
					}
				}
				$sth->finish;


				if ($host_from_this_registry) {
					if ($hostObj =~ /\.$name$/i) {
						$sth = $dbh->prepare("INSERT INTO `host` (`name`,`domain_id`,`clid`,`crid`,`crdate`) VALUES(?,?,?,?,CURRENT_TIMESTAMP)") or die $dbh->errstr;
						$sth->execute($hostObj,$domain_id,$registrar_id,$registrar_id) or die $sth->errstr;
						my $host_id = $dbh->last_insert_id(undef, undef, undef, undef);

						$dbh->do("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES('$domain_id','$host_id')") or die $dbh->errstr;
					}
				}
				else {
					$sth = $dbh->prepare("INSERT INTO `host` (`name`,`clid`,`crid`,`crdate`) VALUES(?,?,?,CURRENT_TIMESTAMP)") or die $dbh->errstr;
					$sth->execute($hostObj,$registrar_id,$registrar_id) or die $sth->errstr;
					my $host_id = $dbh->last_insert_id(undef, undef, undef, undef);

					$dbh->do("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES('$domain_id','$host_id')") or die $dbh->errstr;
				}
			}
		}





		foreach my $node ($hostAttr_list->get_nodelist) {
			my $hostName = $xp->findvalue('domain:hostName[1]', $node);

			my ($hostName_already_exist) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$hostName' LIMIT 1");
			if ($hostName_already_exist) {
				my ($domain_host_map_id) = $dbh->selectrow_array("SELECT `domain_id` FROM `domain_host_map` WHERE `domain_id` = '$domain_id' AND `host_id` = '$hostName_already_exist' LIMIT 1");
				if (!$domain_host_map_id) {
					$dbh->do("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES('$domain_id','$hostName_already_exist')") or die $dbh->errstr;
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

				$dbh->do("INSERT INTO `domain_host_map` (`domain_id`,`host_id`) VALUES('$domain_id','$host_id')") or die $dbh->errstr;

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

					$dbh->do("INSERT INTO `host_addr` (`host_id`,`addr`,`ip`) VALUES('$host_id','$hostAddr','$addr_type')") or die $dbh->errstr;
				}
			}
		}





		foreach my $node ($contact_list->get_nodelist) {
			my $contact = $node->string_value;
			my $contact_type = $node->findvalue('@type[1]');
			$contact = uc($contact);
			my ($contact_id) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$contact' LIMIT 1");
			my $sth = $dbh->prepare("INSERT INTO `domain_contact_map` (`domain_id`,`contact_id`,`type`) VALUES('$domain_id','$contact_id','$contact_type')") or die $dbh->errstr;
			$sth->execute() or die $sth->errstr;
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			# aici de revizuit daca el da la inserare acelas status care exista va fi un internal error
			# de scos eroarea in exterior
			my $sth = $dbh->prepare("INSERT INTO `domain_status` (`domain_id`,`status`) VALUES('$domain_id','$status')") or die $dbh->errstr;
			$sth->execute() or die $sth->errstr;
		}
	}

	#_________________________________________________________________________________________________________________
	if ($domain_chg && $xp->find('./*', $domain_chg)->size > 0) {
		my $registrant_nodes = $xp->find('domain:registrant', $domain_chg); # element that contains the identifier
		if ($registrant_nodes->size) {
			my $registrant = $registrant_nodes->get_node(0)->string_value;
			$registrant = uc($registrant);
			if ($registrant) {
				my ($registrant_id) = $dbh->selectrow_array("SELECT `id` FROM `contact` WHERE `identifier` = '$registrant' LIMIT 1");
				# This object identifier MUST be known to the server before the contact object can be associated with the domain object.
				$dbh->do("UPDATE `domain` SET `registrant` = '$registrant_id', `update` = CURRENT_TIMESTAMP WHERE `id` = '$domain_id'") or die $dbh->errstr;
			}
			else {
				# An empty element can be used to remove registrant information.
				$dbh->do("UPDATE `domain` SET `registrant` = NULL, `update` = CURRENT_TIMESTAMP WHERE `id` = '$domain_id'") or die $dbh->errstr;
			}
		}

		my $authInfo = $xp->find('domain:authInfo', $domain_chg)->get_node(0); # element that contains authorization
		my $authInfo_pw = $xp->findvalue('domain:pw[1]', $authInfo);
		if ($authInfo_pw) {
			my $sth = $dbh->prepare("UPDATE `domain_authInfo` SET `authinfo` = ? WHERE `domain_id` = ? AND `authtype` = ?") or die $dbh->errstr;
			$sth->execute($authInfo_pw,$domain_id,'pw') or die $sth->errstr;
		}
		my $authInfo_ext = $xp->findvalue('domain:ext[1]', $authInfo);
		if ($authInfo_ext) {
			$dbh->do("UPDATE `domain_authInfo` SET `authinfo` = ? WHERE `domain_id` = ? AND `authtype` = ?") or die $dbh->errstr;
			$sth->execute($authInfo_ext,$domain_id,'ext') or die $sth->errstr;
		}
		my $authInfo_null = $xp->findvalue('domain:null[1]', $authInfo);
		if ($authInfo_null) {
			$dbh->do("DELETE FROM `domain_authInfo` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
		}
	}

	#_________________________________________________________________________________________________________________
	if ($rgp_update) {
		my $op_attribute = $xp->findvalue('rgp:restore/@op[1]', $rgp_update); # request|report

		if ($op_attribute eq 'request') {
			my $temp_id = $dbh->selectrow_array("SELECT COUNT(`id`) AS `ids` FROM `domain` WHERE `rgpstatus` = 'redemptionPeriod' AND `id` = '$domain_id' LIMIT 1");
			if ($temp_id == 1) {
				# putem sa punem rgp status pendingRestore
				$dbh->do("UPDATE `domain` SET `rgpstatus` = 'pendingRestore', `resTime` = CURRENT_TIMESTAMP, `update` = CURRENT_TIMESTAMP WHERE `id` = '$domain_id'") or die $dbh->errstr;
				# trebuie de umplut si XML pentru extensie
			}
			else {
				# returnam eroare ca nu se poate, posibil doar la cele care au statut redemptionPeriod
				$blob->{resultCode} = 2304; # Object status prohibits operation
				$blob->{human_readable_message} = 'pendingRestore se poate de facut doar daca domeniul este acuma in redemptionPeriod';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
		elsif ($op_attribute eq 'report') {

# http://tools.ietf.org/html/rfc3915#section-4.2.5
#          <rgp:report>
#            <rgp:preData>Pre-delete registration data goes here. Both XML and free text are allowed.</rgp:preData>
#            <rgp:postData>Post-restore registration data goes here. Both XML and free text are allowed.</rgp:postData>
#            <rgp:delTime>2003-07-10T22:00:00.0Z</rgp:delTime>
#            <rgp:resTime>2003-07-20T22:00:00.0Z</rgp:resTime>
#            <rgp:resReason>Registrant error.</rgp:resReason>
#            <rgp:statement>This registrar has not restored the Registered Name in order to assume the rights to use or sell the Registered Name for itself or for any third party.</rgp:statement>
#            <rgp:statement>The information in this report is true to best of this registrar's knowledge, and this registrar acknowledges that intentionally supplying false information in this report shall constitute an incurable material breach of the Registry-Registrar Agreement.</rgp:statement>
#            <rgp:other>Supporting information goes here.</rgp:other>
#          </rgp:report>

			my $temp_id = $dbh->selectrow_array("SELECT COUNT(`id`) AS `ids` FROM `domain` WHERE `rgpstatus` = 'pendingRestore' AND `id` = '$domain_id' LIMIT 1");
			if ($temp_id == 1) {
				# aici facem o verificare daca are bani pe cont pentru restore si renew un an
				#_________________________________________________________________________________________________________________
				my ($registrar_balance,$creditLimit) = $dbh->selectrow_array("SELECT `accountBalance`,`creditLimit` FROM `registrar` WHERE `id` = '$registrar_id' LIMIT 1");
				my $renew_price = $dbh->selectrow_array("SELECT `m12` FROM `domain_price` WHERE `tldid` = '$tldid' AND `command` = 'renew' LIMIT 1");
				my $restore_price = $dbh->selectrow_array("SELECT `price` FROM `domain_restore_price` WHERE `tldid` = '$tldid' LIMIT 1");

				if (($registrar_balance + $creditLimit) < ($renew_price + $restore_price)) {
					# This response code MUST be returned when a server attempts to execute a billable operation and the command cannot be completed due to a client-billing failure.
					$blob->{resultCode} = 2104; # Billing failure
					$blob->{human_readable_message} = 'Nu sunt bani pe cont pentru restore si renew';
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
				#_________________________________________________________________________________________________________________

				my ($from) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
				$sth = $dbh->prepare("UPDATE `domain` SET `exdate` = DATE_ADD(`exdate`, INTERVAL ? MONTH), `rgpstatus` = NULL, `rgpresTime` = CURRENT_TIMESTAMP, `update` = CURRENT_TIMESTAMP WHERE `id` = ?") or die $dbh->errstr;
				$sth->execute(12,$domain_id) or die $sth->errstr;
				if ($sth->err) {
					my $err = 'UPDATE failed: ' . $sth->errstr;
					$blob->{resultCode} = 2400; # Command failed
					$blob->{human_readable_message} = 'Nu a fost reinnoit cu success, ceva nu este in regula';
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
				else {
					# se va scoate din pendingDelete status
					my $sth = $dbh->prepare("DELETE FROM `domain_status` WHERE `domain_id` = ? AND `status` = ?") or die $dbh->errstr;
					$sth->execute($domain_id,'pendingDelete') or die $sth->errstr;

					# ii luam banii de pe cont
					# ii mai verificam contul daca nu are destui ii punem in poll un mesaj
					# de vazut cu poll sa nu ii punem de mai multe ori acelas mesaj
					#_________________________________________________________________________________________________________________
					$dbh->do("UPDATE `registrar` SET `accountBalance` = (`accountBalance` - ($renew_price + $restore_price)) WHERE `id` = '$registrar_id'") or die $dbh->errstr;
					$dbh->do("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES('$registrar_id',CURRENT_TIMESTAMP,'restore domain $name','-$restore_price')") or die $dbh->errstr;
					$dbh->do("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES('$registrar_id',CURRENT_TIMESTAMP,'renew domain $name for period 12 MONTH','-$renew_price')") or die $dbh->errstr;
					#_________________________________________________________________________________________________________________

					my ($to) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
					$sth = $dbh->prepare("INSERT INTO `statement` (`registrar_id`,`date`,`command`,`domain_name`,`length_in_months`,`from`,`to`,`amount`) VALUES(?,CURRENT_TIMESTAMP,?,?,?,?,?,?)") or die $dbh->errstr;
					$sth->execute($registrar_id,'restore',$name,0,$from,$from,$restore_price) or die $sth->errstr;
					$sth = $dbh->prepare("INSERT INTO `statement` (`registrar_id`,`date`,`command`,`domain_name`,`length_in_months`,`from`,`to`,`amount`) VALUES(?,CURRENT_TIMESTAMP,?,?,?,?,?,?)") or die $dbh->errstr;
					$sth->execute($registrar_id,'renew',$name,12,$from,$to,$renew_price) or die $sth->errstr;
					#_________________________________________________________________________________________________________________
			
					my $curdate_id = $dbh->selectrow_array("SELECT `id` FROM `statistics` WHERE `date` = CURDATE()");
					if (!$curdate_id) {
						$dbh->do("INSERT IGNORE INTO `statistics` (`date`) VALUES(CURDATE())") or die $dbh->errstr;
					}
					$dbh->do("UPDATE `statistics` SET `restored_domains` = `restored_domains` + 1 WHERE `date` = CURDATE()") or die $dbh->errstr;
					$dbh->do("UPDATE `statistics` SET `renewed_domains` = `renewed_domains` + 1 WHERE `date` = CURDATE()") or die $dbh->errstr;
				}
				#============================================================
			}
			else {
				# returnam eroare ca nu se poate, posibil doar la cele care au statut pendingRestore
				$blob->{resultCode} = 2304; # Object status prohibits operation
				$blob->{human_readable_message} = 'report se poate de transmis doar daca domeniul este in pendingRestore status';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
	}

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('host:update',$update_node)->get_node(0)) {
	################################################################
	#
	#			<update><host:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-host:update';
	$blob->{command} = 'update_host';
	$blob->{obj_type} = 'host';

	# -  A <host:name> element that contains the fully qualified name of the host object to be updated.
	my $name = $xp->findvalue('host:name[1]', $obj);
	$blob->{obj_id} = $name;

	my $host_rem = $xp->find('host:rem', $obj)->get_node(0);
	my $host_add = $xp->find('host:add', $obj)->get_node(0);
	my $host_chg = $xp->find('host:chg', $obj)->get_node(0);

	my $extension = 0;

	if (!($host_rem && $xp->find('./*', $host_rem)->size > 0) && !($host_add && $xp->find('./*', $host_add)->size > 0) && !($host_chg && $xp->find('./*', $host_chg)->size > 0)) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'At least one host:rem || host:add || host:chg MUST be provided';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if (!$name) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Nu este indicat hostul care se updateaza';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$name = uc($name);
	my ($host_id,$registrar_id_host) = $dbh->selectrow_array("SELECT `id`,`clid` FROM `host` WHERE `name` = '$name' LIMIT 1");
	if (!$host_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'Nu este asa host in registry';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ($registrar_id != $registrar_id_host) {
		$blob->{resultCode} = 2201; # Authorization error
		$blob->{human_readable_message} = 'Not registrar for host, Authorization error = 2201';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my $sth = $dbh->prepare("SELECT `status` FROM `host_status` WHERE `host_id` = ?") or die $dbh->errstr;
	$sth->execute($host_id) or die $sth->errstr;
	while (my ($status) = $sth->fetchrow_array()) {
		if (($status =~ m/.*(serverUpdateProhibited)$/) || ($status =~ /^pending/)) {
			$blob->{resultCode} = 2304; # Object status prohibits operation
			$blob->{human_readable_message} = 'Are un status serverUpdateProhibited sau pendingUpdate care nu permite modificarea, mai intii schimba statutul apoi faci update, de mai studiat interpretarile EPP 5730 aici';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}

	# verificam daca are restrictii la update, daca da apoi mai jos verificam daca o venit rem la acest status, daca nu exista rem, apoi returnam error
	my $clientUpdateProhibited = 0;
	($clientUpdateProhibited) = $dbh->selectrow_array("SELECT `id` FROM `host_status` WHERE `host_id` = '$host_id' AND `status` = 'clientUpdateProhibited' LIMIT 1");

	# mai intii verificam tot ce intra, daca totul este conform RFC si conform policy, ap doar atunci facem update
	#_________________________________________________________________________________________________________________
	if ($host_rem) {
		my $addr_list = $xp->find('host:addr', $host_rem); # One or more
		my $status_list = $xp->find('host:status/@s', $host_rem); # One or more

		if ($addr_list->size == 0 && $status_list->size == 0) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'At least one element MUST be present';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			if ($status eq 'clientUpdateProhibited') {
				$clientUpdateProhibited = 0;
			}
			if ($status !~ /^(clientDeleteProhibited|clientUpdateProhibited)$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Sunt acceptate doar aceste status-uri clientDeleteProhibited|clientUpdateProhibited';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
	}

	if ($clientUpdateProhibited) {
		# a ramas de verificat aici
		$blob->{resultCode} = 2304; # Object status prohibits operation
		$blob->{human_readable_message} = 'Are status clientUpdateProhibited dar tu nu ai indicat acest status la stergere';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}
	#_________________________________________________________________________________________________________________
	if ($host_add) {
		my $addr_list = $xp->find('host:addr', $host_add); # One or more
		my $status_list = $xp->find('host:status/@s', $host_add); # One or more

		if ($addr_list->size == 0 && $status_list->size == 0) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'At least one element MUST be present';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			if ($status !~ /^(clientDeleteProhibited|clientUpdateProhibited)$/) {
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = 'Sunt acceptate doar aceste status-uri clientDeleteProhibited|clientUpdateProhibited';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}

			if ($xp->find('host:status[@s="'.$status.'"]', $host_rem)->size == 0) {
				my ($contact_status_id) = $dbh->selectrow_array("SELECT `id` FROM `host_status` WHERE `host_id` = '$host_id' AND `status` = '$status' LIMIT 1");
				if ($contact_status_id) {
					$blob->{resultCode} = 2306; # Parameter value policy error
					$blob->{human_readable_message} = "This status '$status' already exists for this host";
						$blob->{optionalValue} = 1;
						$blob->{xmlns_obj} = 'xmlns:host';
						$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:host-1.0';
						$blob->{obj_elem} = 'host:status';
						$blob->{obj_elem_value} = $status;
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
			}
		}

		foreach my $node ($addr_list->get_nodelist) {
			my $addr = $node->string_value;
			my $addr_type = $node->findvalue('@ip[1]') || 'v4';
			if ($addr_type eq 'v6') {
				if ($addr =~ m/^[\da-fA-F]{1,4}(:[\da-fA-F]{1,4}){7}$/ || $addr =~ m/^::$/ || $addr =~ m/^([\da-fA-F]{1,4}:){1,7}:$/ || $addr =~ m/^[\da-fA-F]{1,4}:(:[\da-fA-F]{1,4}){1,6}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){2}(:[\da-fA-F]{1,4}){1,5}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){3}(:[\da-fA-F]{1,4}){1,4}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){4}(:[\da-fA-F]{1,4}){1,3}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){5}(:[\da-fA-F]{1,4}){1,2}$/ || $addr =~ m/^([\da-fA-F]{1,4}:){6}:[\da-fA-F]{1,4}$/) {
					# true
					$addr = _normalise_v6_address($addr);
					# aceasta combinatie trebuie sa fie unica
					my ($ipv6_addr_already_exists) = $dbh->selectrow_array("SELECT `id` FROM `host_addr` WHERE `host_id` = '$host_id' AND `addr` = '$addr' AND `ip` = '6' LIMIT 1");
					if ($ipv6_addr_already_exists) {
						$blob->{resultCode} = 2306; # Parameter value policy error
						$blob->{human_readable_message} = "This addr '$addr' already exists for this host";
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
					$addr = _normalise_v4_address($addr);
					# aceasta combinatie trebuie sa fie unica
					my ($ipv4_addr_already_exists) = $dbh->selectrow_array("SELECT `id` FROM `host_addr` WHERE `host_id` = '$host_id' AND `addr` = '$addr' AND `ip` = '4' LIMIT 1");
					if ($ipv4_addr_already_exists) {
						$blob->{resultCode} = 2306; # Parameter value policy error
						$blob->{human_readable_message} = "This addr '$addr' already exists for this host";
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
		}
	}
	#_________________________________________________________________________________________________________________
	if ($host_chg) {
		# -  A <host:name> element that contains a new fully qualified host name by which the host object will be known.
		my $chg_name = $xp->findvalue('host:name[1]', $host_chg);

		#if ($chg_name =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){0,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($chg_name) < 254) {
		if ($chg_name =~ m/^([A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9]){0,1}\.){1,125}[A-Z0-9]([A-Z0-9-]{0,61}[A-Z0-9])$/i && length($chg_name) < 254) {
			# verificam daca nu cumva un asa host deja exista, daca exista returnam eroare, deoarece nu pot exista 2 hosturi cu nume identic
			# aici mai trebuie revizuit conform rfc
			my ($chg_name_id) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$chg_name' LIMIT 1");
			if ($chg_name_id) {
				$blob->{resultCode} = 2306; # Parameter value policy error
				$blob->{human_readable_message} = 'Daca deja exista apoi nu putem sa-l schimbam cred ca, vezi ce zic altii si RFC pe tema asta';
					$blob->{optionalValue} = 1;
					$blob->{xmlns_obj} = 'xmlns:host';
					$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:host-1.0';
					$blob->{obj_elem} = 'host:name';
					$blob->{obj_elem_value} = $chg_name;
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
		else {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Invalid host:name';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# verificam daca hostul vechi are domain_id, daca da, apoi denumirea noua trebuie sa fie subordinate
		my ($domain_id) = $dbh->selectrow_array("SELECT `domain_id` FROM `host` WHERE `name` = '$name' LIMIT 1");
		if ($domain_id) {
			# aducem numele de domeniu, pentru a compara cu $chg_name
			my ($domain_name) = $dbh->selectrow_array("SELECT `name` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");

			# facem comparatie intre $chg_name si $domain_name
			if ($chg_name =~ /\.$domain_name$/i) {
				# este ok
			}
			else {
				# returnam eroare, ca nu corespunde
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = "Trebuie sa fie subdomeniu la $domain_name";
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
		else {
			# este external host
			# poate aici sa facem un verify din sistema sa vedem daca in DNS exista asa host
			# dar asta e optional, de obicei nu se face asta, doar francezii si nemtii fac asa ceva
			# verificam daca nu cumva vrea sa fie internal host, daca este internal atunci dam eroare
			my $internal_host = 0;
			my $sth = $dbh->prepare("SELECT `tld` FROM `domain_tld`") or die $dbh->errstr;
			$sth->execute() or die $sth->errstr;
			while (my ($tld) = $sth->fetchrow_array()) {
				$tld = uc($tld);
				$tld =~ s/\./\\./g;
				if ($chg_name =~ /$tld$/i) {
					$internal_host = 1;
					last;
				}
			}
			$sth->finish;

			if ($internal_host) {
				# returnam eroare
				$blob->{resultCode} = 2005; # Parameter value syntax error
				$blob->{human_readable_message} = "Must be external host";
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		# verificam daca hostul actual undeva se foloseste in calitate de NS, daca da atunci nu putem sa-l modificam

#  Host name changes MAY require the addition or removal of IP addresses
#  to be accepted by the server.  IP address association MAY be subject
#  to server policies for provisioning hosts as name servers.

#  Host name changes can have an impact on associated objects that refer
#  to the host object.  A host name change SHOULD NOT require additional
#  updates of associated objects to preserve existing associations, with
#  one exception: changing an external host object that has associations
#  with objects that are sponsored by a different client.  Attempts to
#  update such hosts directly MUST fail with EPP error code 2305.  The
#  change can be provisioned by creating a new external host with a new
#  name and any needed new attributes, and subsequently updating the
#  other objects sponsored by the client.

#		my ($domain_host_map_id) = $dbh->selectrow_array("SELECT `domain_id` FROM `domain_host_map` WHERE `host_id` = '$host_id' LIMIT 1");
		my ($domain_host_map_id) = $dbh->selectrow_array("SELECT `h`.`id` FROM `host` AS `h`
			INNER JOIN `domain_host_map` AS `dhm` ON (`dhm`.`host_id` = `h`.`id`)
			INNER JOIN `domain` AS `d` ON (`d`.`id` = `dhm`.`domain_id` AND `d`.`clid` != `h`.`clid`)
			WHERE `h`.`id` = '$host_id' AND `h`.`domain_id` IS NULL
			LIMIT 1");

		if ($domain_host_map_id) {
			# update command is attempted and fails due to existing object relationships
			$blob->{resultCode} = 2305; # Object association prohibits operation
			$blob->{human_readable_message} = 'Nu este posibil de modificat deoarece este dependenta, este folosit de careva domeniu in calitate de NS';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}





	#_________________________________________________________________________________________________________________
	if ($host_rem) {
		my $addr_list = $xp->find('host:addr', $host_rem); # One or more
		my $status_list = $xp->find('host:status/@s', $host_rem); # One or more

		foreach my $node ($addr_list->get_nodelist) {
			my $addr = $node->string_value;
			my $addr_type = $node->findvalue('@ip[1]') || 'v4';
			my $sth = $dbh->prepare("DELETE FROM `host_addr` WHERE `host_id` = ? AND `addr` = ? AND `ip` = ?") or die $dbh->errstr;
			$sth->execute($host_id,$addr,$addr_type) or die $sth->errstr;
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			my $sth = $dbh->prepare("DELETE FROM `host_status` WHERE `host_id` = ? AND `status` = ?") or die $dbh->errstr;
			$sth->execute($host_id,$status) or die $sth->errstr;
		}
	}

	#_________________________________________________________________________________________________________________
	if ($host_add) {
		my $addr_list = $xp->find('host:addr', $host_add); # One or more
		my $status_list = $xp->find('host:status/@s', $host_add); # One or more

		foreach my $node ($addr_list->get_nodelist) {
			my $addr = $node->string_value;
			my $addr_type = $node->findvalue('@ip[1]') || 'v4';

			# normalise
			if ($addr_type eq 'v6') {
				$addr = _normalise_v6_address($addr);
			}
			else {
				$addr = _normalise_v4_address($addr);
			}

			# aici de revizuit daca el da la inserare acelas address care exista va fi un internal error
			# de prevenit asa situatie
			my $sth = $dbh->prepare("INSERT INTO `host_addr` (`host_id`,`addr`,`ip`) VALUES(?,?,?)") or die $dbh->errstr;
			$sth->execute($host_id,$addr,$addr_type) or die $sth->errstr;
		}

		foreach my $node ($status_list->get_nodelist) {
			my $status = $node->string_value;
			# aici de revizuit daca el da la inserare acelas status care exista va fi un internal error
			# de prevenit asa situatie
			my $sth = $dbh->prepare("INSERT INTO `host_status` (`host_id`,`status`) VALUES(?,?)") or die $dbh->errstr;
			$sth->execute($host_id,$status) or die $sth->errstr;
		}
	}
	#_________________________________________________________________________________________________________________
	if ($host_chg) {
		# -  A <host:name> element that contains a new fully qualified host name by which the host object will be known.
		my $chg_name = $xp->findvalue('host:name[1]', $host_chg);
		$chg_name = uc($chg_name);
		# cred ca trebuie sa mai verificam aici ceva , ca e tare incurcat dupa RFC
		my ($chg_name_id) = $dbh->selectrow_array("SELECT `id` FROM `host` WHERE `name` = '$chg_name' LIMIT 1");
		my $sth = $dbh->prepare("UPDATE `host` SET `name` = ?, `update` = CURRENT_TIMESTAMP WHERE `name` = ?") or die $dbh->errstr;
		$sth->execute($chg_name,$name) or die $sth->errstr;
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
	$blob->{human_readable_message} = 'comanda necunoscuta';
	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}


sub _normalise_v4_address {
	my ($v4) = @_;

	$v4 =~ s/^0+(\d)/$1/;     # remove leading zeros from the first octet
	$v4 =~ s/\.0+(\d)/.$1/g;  # remove leading zeros from successive octets

	return ($v4);
}


sub _normalise_v6_address {
	my ($v6) = @_;

	$v6 =~ uc $v6;               # upper case any alphabetics
	$v6 =~ s/^0+([\dA-F])/$1/;   # remove leading zeros from the first word
	$v6 =~ s/:0+([\dA-F])/:$1/g; # remove leading zeros from successive words

	$v6 =~ s/:0:0:/::/           # introduce a :: if there isn't one already
	unless ($v6 =~ m/::/);

	$v6 =~ s/^0+::/::/;          # remove initial zero word before a ::
	$v6 =~ s/(:0)+::/::/;        # remove other zero words before a ::
	$v6 =~ s/:(:0)+/:/;          # remove zero words following a ::

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