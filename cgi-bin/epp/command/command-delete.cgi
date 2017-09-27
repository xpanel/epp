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
$blob->{cmd} = 'delete';

my $node = $xp->findnodes('/epp:epp/epp:command/epp:delete')->get_node(0);
my ($registrar_id) = $dbh->selectrow_array("SELECT `id` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

my $obj;
if ($obj = $xp->find('contact:delete',$node)->get_node(0)) {
	################################################################
	#
	#			<delete><contact:id>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-contact:delete';
	$blob->{command} = 'delete_contact';
	$blob->{obj_type} = 'contact';

	# -  A <contact:id> element that contains the server-unique identifier of the contact object to be deleted.
	my $identifier = $xp->findvalue('contact:id[1]', $obj);
	$blob->{obj_id} = $identifier;

	if (!$identifier) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Missing contact:id';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($contact_id,$registrar_id_contact) = $dbh->selectrow_array("SELECT `id`,`clid` FROM `contact` WHERE `identifier` = '$identifier' LIMIT 1");
	if (!$contact_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'contact:id does not exist';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ($registrar_id != $registrar_id_contact) {
		$blob->{resultCode} = 2201; # Authorization error
		$blob->{human_readable_message} = 'Alt registrar';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($registrant_exists) = $dbh->selectrow_array("SELECT `id` FROM `domain` WHERE `registrant` = '$contact_id' LIMIT 1");
	if ($registrant_exists) {
		# delete command is attempted and fails due to existing object relationships
		$blob->{resultCode} = 2305; # Object association prohibits operation
		$blob->{human_readable_message} = 'Acest contact este asociat unui domeniu ca registrant';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($contact_in_use) = $dbh->selectrow_array("SELECT `id` FROM `domain_contact_map` WHERE `contact_id` = '$contact_id' LIMIT 1");
	if ($contact_in_use) {
		$blob->{resultCode} = 2305;
		$blob->{human_readable_message} = 'Acest contact este asociat unui domeniu';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my $sth = $dbh->prepare("SELECT `status` FROM `contact_status` WHERE `contact_id` = ?") or die $dbh->errstr;
	$sth->execute($contact_id) or die $sth->errstr;
	while (my ($status) = $sth->fetchrow_array()) {
		if (($status =~ m/.*(UpdateProhibited|DeleteProhibited)$/) || ($status =~ /^pending/)) {
			$blob->{resultCode} = 2304; # Object status prohibits operation
			$blob->{human_readable_message} = 'Are un status care nu permite stergerea';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	$sth->finish;

	$sth = $dbh->prepare("DELETE FROM `contact_postalInfo` WHERE `contact_id` = ?") or die $dbh->errstr;
	$sth->execute($contact_id) or die $sth->errstr;

	$sth = $dbh->prepare("DELETE FROM `contact_authInfo` WHERE `contact_id` = ?") or die $dbh->errstr;
	$sth->execute($contact_id) or die $sth->errstr;

	$sth = $dbh->prepare("DELETE FROM `contact_status` WHERE `contact_id` = ?") or die $dbh->errstr;
	$sth->execute($contact_id) or die $sth->errstr;

    $sth = $dbh->prepare("DELETE FROM `contact` WHERE `id` = ?") or die $dbh->errstr;
    $sth->execute($contact_id);
	if ($sth->err) {
		#my $err = 'DELETE failed: ' . $sth->errstr;
		$blob->{resultCode} = 2400; # Command failed
		$blob->{human_readable_message} = 'Nu am reusit sa sterg contactul, probabil are legaturi catre alte obiecte';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('domain:delete',$node)->get_node(0)) {
	################################################################
	#
	#			<delete><domain:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-domain:delete';
	$blob->{command} = 'delete_domain';
	$blob->{obj_type} = 'domain';

	# -  A <domain:name> element that contains the fully qualified name of the domain object to be deleted.
	my $name = $xp->findvalue('domain:name[1]', $obj);
	$blob->{obj_id} = $name;

	if (!$name) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Rog sa specificati numele de domeniu care va fi sters';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($domain_id,$tldid,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$rgpstatus,$addPeriod,$autoRenewPeriod,$renewPeriod,$renewedDate,$transferPeriod) = $dbh->selectrow_array("SELECT `id`,`tldid`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`rgpstatus`,`addPeriod`,`autoRenewPeriod`,`renewPeriod`,`renewedDate`,`transferPeriod` FROM `domain` WHERE `name` = '$name' LIMIT 1");
	if (!$domain_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'domain:name does not exist';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ($registrar_id != $registrar_id_domain) {
		# not registrar for domain
		$blob->{resultCode} = 2201; # Authorization error
		$blob->{human_readable_message} = 'Este alt registrar';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my $sth = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
	$sth->execute($domain_id) or die $sth->errstr;
	while (my ($status) = $sth->fetchrow_array()) {
		if (($status =~ m/.*(UpdateProhibited|DeleteProhibited)$/) || ($status =~ /^pending/)) {
			# This response code MUST be returned when a server receives a command to transform an object that cannot be completed due to server policy or business practices.
			$blob->{resultCode} = 2304; # Object status prohibits operation
			$blob->{human_readable_message} = 'Numele de domeniu are un status care nu permite stergerea';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	$sth->finish;

	# aici va fi o matematica complicata unde noi vom returna banii inapoi pentru Status Values
	# se vor inscrie in balance banii pusi inapoi
	my $grace_period = 30;
	$dbh->do("DELETE FROM `domain_status` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
	$dbh->do("UPDATE `domain` SET `rgpstatus` = 'redemptionPeriod', `delTime` = DATE_ADD(CURRENT_TIMESTAMP, INTERVAL $grace_period DAY) WHERE `id` = '$domain_id'") or die $dbh->errstr;
	$dbh->do("INSERT INTO `domain_status` (`domain_id`,`status`) VALUES('$domain_id','pendingDelete')") or die $dbh->errstr;

	# <registry:gracePeriod command="create" unit="d">5</registry:gracePeriod>
	# <registry:gracePeriod command="renew" unit="d">5</registry:gracePeriod>
	# <registry:gracePeriod command="transfer" unit="d">5</registry:gracePeriod>
	# <registry:gracePeriod command="autoRenew" unit="d">45</registry:gracePeriod>

	if ($rgpstatus) {
		if ($rgpstatus eq 'addPeriod') {
			# verificam daca se incadreaza in intervalul de 5 zile dupa inregistrare
			my ($addPeriod_id) = $dbh->selectrow_array("SELECT `id` FROM `domain` WHERE `id` = '$domain_id' AND (CURRENT_TIMESTAMP < DATE_ADD(`crdate`, INTERVAL 5 DAY)) LIMIT 1");
			if ($addPeriod_id) {
				# ii dam banii inapoi
				my ($price) = $dbh->selectrow_array("SELECT `m$addPeriod` FROM `domain_price` WHERE `tldid` = '$tldid' AND `command` = 'create' LIMIT 1");
				if (!defined($price)) {
					$blob->{resultCode} = 2400; # Command failed
					$blob->{human_readable_message} = 'Nu este declarat pretul, perioada si valuta pentru asa TLD';
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
				#_________________________________________________________________________________________________________________
				$sth = $dbh->prepare("UPDATE `registrar` SET `accountBalance` = (`accountBalance` + ?) WHERE `id` = ?") or die $dbh->errstr;
				$sth->execute($price,$registrar_id) or die $sth->errstr;

				$sth = $dbh->prepare("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES(?,CURRENT_TIMESTAMP,'domain name is deleted by the registrar during grace addPeriod, the registry provides a credit for the cost of the registration domain $name for period $addPeriod MONTH',?)") or die $dbh->errstr;
				$sth->execute($registrar_id,$price) or die $sth->errstr;

				# If a domain is deleted within the Add Grace Period, then the Registrar is credited the registration, taking into account the number of years 
				# for which the registration were done. The domain is removed from the Registry database and is immediately available for registration by any Registrar.

					# aici facem stergerea propriu zisa
					#----- start simple delete ------------------------------------------
					# A domain object SHOULD NOT be deleted if subordinate host objects are associated with the domain object.
					$sth = $dbh->prepare("SELECT `id` FROM `host` WHERE `domain_id` = ?") or die $dbh->errstr;
					$sth->execute($domain_id) or die $sth->errstr;
					while (my ($host_id) = $sth->fetchrow_array()) {
						$dbh->do("DELETE FROM `host_addr` WHERE `host_id` = '$host_id'") or die $dbh->errstr;
						$dbh->do("DELETE FROM `host_status` WHERE `host_id` = '$host_id'") or die $dbh->errstr;
						$dbh->do("DELETE FROM `domain_host_map` WHERE `host_id` = '$host_id'") or die $dbh->errstr;
					}
					$sth->finish;
				
					$dbh->do("DELETE FROM `domain_contact_map` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
					$dbh->do("DELETE FROM `domain_host_map` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
					$dbh->do("DELETE FROM `domain_authInfo` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
					$dbh->do("DELETE FROM `domain_status` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
					$dbh->do("DELETE FROM `host` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
				
					$sth = $dbh->prepare("DELETE FROM `domain` WHERE `id` = ?");
					$sth->execute($domain_id);
					if ($sth->err) {
						#my $err = 'DELETE failed: ' . $sth->errstr;
						$blob->{resultCode} = 2400; # Command failed
						$blob->{human_readable_message} = 'Numele de domeniu nu a fost sters cred ca este vre-o legatura cu alte obiecte';
						my $msg = epp_writer($blob);
						print $msg;
						my $uptr = update_transaction($msg);
						exit;
					}
				
					my $curdate_id = $dbh->selectrow_array("SELECT `id` FROM `statistics` WHERE `date` = CURDATE()");
					if (!$curdate_id) {
						$dbh->do("INSERT IGNORE INTO `statistics` (`date`) VALUES(CURDATE())") or die $dbh->errstr;
					}
					$dbh->do("UPDATE `statistics` SET `deleted_domains` = `deleted_domains` + 1 WHERE `date` = CURDATE()") or die $dbh->errstr;
					#----- end simple delete ------------------------------------------

			}
		}
		elsif ($rgpstatus eq 'autoRenewPeriod') {
			# verificam daca se incadreaza in intervalul de 45 zile dupa reinnoire
			my ($autoRenewPeriod_id) = $dbh->selectrow_array("SELECT `id` FROM `domain` WHERE `id` = '$domain_id' AND (CURRENT_TIMESTAMP < DATE_ADD(`renewedDate`, INTERVAL 45 DAY)) LIMIT 1");
			if ($autoRenewPeriod_id) {
				# ii dam banii inapoi
				my ($price) = $dbh->selectrow_array("SELECT `m$autoRenewPeriod` FROM `domain_price` WHERE `tldid` = '$tldid' AND `command` = 'renew' LIMIT 1");
				if (!defined($price)) {
					$blob->{resultCode} = 2400; # Command failed
					$blob->{human_readable_message} = 'Nu este declarat pretul, perioada si valuta pentru asa TLD';
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
				#_________________________________________________________________________________________________________________
				$sth = $dbh->prepare("UPDATE `registrar` SET `accountBalance` = (`accountBalance` + ?) WHERE `id` = ?") or die $dbh->errstr;
				$sth->execute($price,$registrar_id) or die $sth->errstr;

				$sth = $dbh->prepare("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES(?,CURRENT_TIMESTAMP,'domain name is deleted by the registrar during grace autoRenewPeriod, the registry provides a credit for the cost of the renewal domain $name for period $autoRenewPeriod MONTH',?)") or die $dbh->errstr;
				$sth->execute($registrar_id,$price) or die $sth->errstr;
			}
		}
		elsif ($rgpstatus eq 'renewPeriod') {
			# verificam daca se incadreaza in intervalul de 5 zile dupa reinnoire
			my ($renewPeriod_id) = $dbh->selectrow_array("SELECT `id` FROM `domain` WHERE `id` = '$domain_id' AND (CURRENT_TIMESTAMP < DATE_ADD(`renewedDate`, INTERVAL 5 DAY)) LIMIT 1");
			if ($renewPeriod_id) {
				# ii dam banii inapoi
				my ($price) = $dbh->selectrow_array("SELECT `m$renewPeriod` FROM `domain_price` WHERE `tldid` = '$tldid' AND `command` = 'renew' LIMIT 1");
				if (!defined($price)) {
					$blob->{resultCode} = 2400; # Command failed
					$blob->{human_readable_message} = 'Nu este declarat pretul, perioada si valuta pentru asa TLD';
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
				#_________________________________________________________________________________________________________________
				$sth = $dbh->prepare("UPDATE `registrar` SET `accountBalance` = (`accountBalance` + ?) WHERE `id` = ?") or die $dbh->errstr;
				$sth->execute($price,$registrar_id) or die $sth->errstr;

				$sth = $dbh->prepare("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES(?,CURRENT_TIMESTAMP,'domain name is deleted by the registrar during grace renewPeriod, the registry provides a credit for the cost of the renewal domain $name for period $renewPeriod MONTH',?)") or die $dbh->errstr;
				$sth->execute($registrar_id,$price) or die $sth->errstr;
			}
		}
		elsif ($rgpstatus eq 'transferPeriod') {
			# verificam daca se incadreaza in intervalul de 5 zile dupa transfer
			my ($transferPeriod_id) = $dbh->selectrow_array("SELECT `id` FROM `domain` WHERE `id` = '$domain_id' AND (CURRENT_TIMESTAMP < DATE_ADD(`trdate`, INTERVAL 5 DAY)) LIMIT 1");
			if ($transferPeriod_id) {
				# ii dam banii inapoi daca la transfer a fost facut si un renew
				if ($transferPeriod > 0) {
					my ($price) = $dbh->selectrow_array("SELECT `m$transferPeriod` FROM `domain_price` WHERE `tldid` = '$tldid' AND `command` = 'renew' LIMIT 1");
					if (!defined($price)) {
						$blob->{resultCode} = 2400; # Command failed
						$blob->{human_readable_message} = 'Nu este declarat pretul, perioada si valuta pentru asa TLD';
						my $msg = epp_writer($blob);
						print $msg;
						my $uptr = update_transaction($msg);
						exit;
					}
					#_________________________________________________________________________________________________________________
					$sth = $dbh->prepare("UPDATE `registrar` SET `accountBalance` = (`accountBalance` + ?) WHERE `id` = ?") or die $dbh->errstr;
					$sth->execute($price,$registrar_id) or die $sth->errstr;

					$sth = $dbh->prepare("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES(?,CURRENT_TIMESTAMP,'domain name is deleted by the registrar during grace transferPeriod, the registry provides a credit for the cost of the transfer domain $name for period $transferPeriod MONTH',?)") or die $dbh->errstr;
					$sth->execute($registrar_id,$price) or die $sth->errstr;
				}
			}
		}
	}
	$blob->{resultCode} = 1001;

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('host:delete',$node)->get_node(0)) {
	################################################################
	#
	#			<delete><host:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-host:delete';
	$blob->{command} = 'delete_host';
	$blob->{obj_type} = 'host';

	# -  A <host:name> element that contains the fully qualified name of the host object to be deleted.
	my $name = $xp->findvalue('host:name[1]', $obj);
	$blob->{obj_id} = $name;

	if (!$name) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Specifica te rog hostname';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($host_id,$registrar_id_host) = $dbh->selectrow_array("SELECT `id`,`clid` FROM `host` WHERE `name` = '$name' LIMIT 1");
	if (!$host_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'host:name does not exist';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	if ($registrar_id != $registrar_id_host) {
		$blob->{resultCode} = 2201; # Authorization error
		$blob->{human_readable_message} = 'host:name apartine altui registrar';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# A host name object SHOULD NOT be deleted if the host object is associated with any other object.  For example, if the host object is
	# associated with a domain object, the host object SHOULD NOT be deleted until the existing association has been broken.
	# Deleting a host object without first breaking existing associations can cause DNS resolution failure for domain objects that refer to the deleted host object.
	my ($nameserver_inuse) = $dbh->selectrow_array("SELECT `domain_id` FROM `domain_host_map` WHERE `host_id` = '$host_id' LIMIT 1");
	if ($nameserver_inuse) {
		# delete command is attempted and fails due to existing object relationships
		$blob->{resultCode} = 2305; # Object association prohibits operation
		$blob->{human_readable_message} = 'Nu este posibil de sters deoarece este dependenta, este folosit de careva domeniu';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$dbh->do("DELETE FROM `host_addr` WHERE `host_id` = '$host_id'") or die $dbh->errstr;
	$dbh->do("DELETE FROM `host_status` WHERE `host_id` = '$host_id'") or die $dbh->errstr;

    my $sth = $dbh->prepare("DELETE FROM `host` WHERE `id` = ?") or die $dbh->errstr;
    $sth->execute($host_id) or die $sth->errstr;
	if ($sth->err) {
		#my $err = 'DELETE failed: ' . $sth->errstr;
		$blob->{resultCode} = 2400; # Command failed
		$blob->{human_readable_message} = 'Nu a fost sters host-ul, cred ca depinde de alte obiecte';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
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

sub update_transaction {
	my $svframe = shift;
	my $sth = $dbh->prepare("UPDATE `registryTransaction`.`transaction_identifier` SET `cmd` = ?, `obj_type` = ?, `obj_id` = ?, `code` = ?, `msg` = ?, `svTRID` = ?, `svTRIDframe` = ?, `svdate` = ?, `svmicrosecond` = ? WHERE `id` = ?") or die $dbh->errstr;
	my $date_for_sv_transaction = microsecond();
	my ($svdate,$svmicrosecond) = split(/\./, $date_for_sv_transaction);
	$sth->execute($blob->{cmd},$blob->{obj_type},$blob->{obj_id},$blob->{resultCode},$blob->{human_readable_message},$blob->{svTRID},$svframe,$svdate,$svmicrosecond,$transaction_id) or die $sth->errstr;
	return 1;
}