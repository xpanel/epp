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
#	(c) Copyright 2014 XPanel Ltd.
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

my $blob = {};
$blob->{clTRID} = $cltrid;
$blob->{resultCode} = 1000;
$blob->{cmd} = 'transfer';

my $node = $xp->findnodes('/epp:epp/epp:command/epp:transfer')->get_node(0);
my ($registrar_id) = $dbh->selectrow_array("SELECT `id` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

my $obj;
my $op = $node->findvalue('@op[1]');
if ($obj = $xp->find('contact:transfer',$node)->get_node(0)) {
	################################################################
	#
	#			<transfer><contact:id>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-contact:transfer';
	$blob->{command} = 'transfer_contact';
	$blob->{obj_type} = 'contact';

	# -  A <contact:id> element that contains the server-unique identifier of the contact object for which a transfer request is to be created, approved, rejected, or cancelled.
	my $identifier = $xp->findvalue('contact:id[1]', $obj);
	$blob->{obj_id} = $identifier;

	# -  An OPTIONAL <contact:authInfo> pentru op="query" si obligatoriu pentru celelalte valori ale op="approve|cancel|reject|request"
	my $authInfo_pw = $xp->findvalue('contact:authInfo/contact:pw[1]', $obj);

	if (!$identifier) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Indica contact id';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$identifier = uc($identifier);
	my ($contact_id,$registrar_id_contact) = $dbh->selectrow_array("SELECT `id`,`clid` FROM `contact` WHERE `identifier` = '$identifier' LIMIT 1");
	if (!$contact_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'Nu exista asa contact in registry';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# A server MAY automatically approve or reject all transfer requests that are not explicitly approved or rejected by the current sponsoring client within a fixed amount of time.
	# de obicei Registry le aproba automat daca nu sunt aprobate de Losing Registrar
	#_________________________________________________________________________________________________________________
	if ($op eq 'approve') {
		# doar CEL CARE PIERDE (Losing Registrar) poate sa aprobe sau sa rejecteze
		if ($registrar_id != $registrar_id_contact) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'Doar losing registrar poate sa aprobe';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# -  A <contact:authInfo> element that contains authorization information associated with the contact object.
		# de revizuit
		if ($authInfo_pw) {
			my ($contact_authinfo_id) = $dbh->selectrow_array("SELECT `id` FROM `contact_authInfo` WHERE `contact_id` = '$contact_id' AND `authtype` = 'pw' AND `authinfo` = '$authInfo_pw' LIMIT 1");
			if (!$contact_authinfo_id) {
				$blob->{resultCode} = 2202; # Invalid authorization information
				$blob->{human_readable_message} = 'authInfo pw nu este corecta';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		my ($crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
		if ($trstatus eq 'pending') {
			# The losing registrar has five days once the contact is pending to respond.
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
			# totul ce e legat de aprove facem aici

			my $sth = $dbh->prepare("UPDATE `contact` SET `update` = CURRENT_TIMESTAMP, `clid` = '$reid', `upid` = '$registrar_id', `trdate` = CURRENT_TIMESTAMP, `trstatus` = 'clientApproved', `acdate` = CURRENT_TIMESTAMP WHERE `id` = ?") or die $dbh->errstr;
			$sth->execute($contact_id) or die $sth->errstr;

			if ($sth->err) {
				my $err = 'UPDATE failed: ' . $sth->errstr;
				$blob->{resultCode} = 2400; # Command failed
				$blob->{human_readable_message} = 'Nu a fost Approved transferul cu success, ceva nu este in regula';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			else {
				# selectam datele despre starea contactului
				my ($crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
				my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
				my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");
				$blob->{id} = $identifier;
				$blob->{trStatus} = $trstatus;
				$blob->{reID} = $reid_identifier;
				$redate =~ s/\s/T/g;
				$redate .= '.0Z';
				$blob->{reDate} = $redate;
				$blob->{acID} = $acid_identifier;
				$acdate =~ s/\s/T/g;
				$acdate .= '.0Z';
				$blob->{acDate} = $acdate;
				$blob->{resultCode} = 1000; # Command completed successfully
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
			}
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
		}
		else {
			$blob->{resultCode} = 2301; # Object not pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the contact is NOT pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	#_________________________________________________________________________________________________________________
	elsif ($op eq 'cancel') {
		# doar SOLICITANTUL (Requesting or 'Gaining' Registrar) poate face cancel
		if ($registrar_id == $registrar_id_contact) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'Doar SOLICITANTUL poate face cancel';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# -  A <contact:authInfo> element that contains authorization information associated with the contact object.
		# de revizuit
		if ($authInfo_pw) {
			my ($contact_authinfo_id) = $dbh->selectrow_array("SELECT `id` FROM `contact_authInfo` WHERE `contact_id` = '$contact_id' AND `authtype` = 'pw' AND `authinfo` = '$authInfo_pw' LIMIT 1");
			if (!$contact_authinfo_id) {
				$blob->{resultCode} = 2202; # Invalid authorization information
				$blob->{human_readable_message} = 'authInfo pw nu este corecta';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		my ($crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
		if ($trstatus eq 'pending') {
			# The losing registrar has five days once the contact is pending to respond.
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
			# totul ce e legat de cancel facem aici
			my $sth = $dbh->prepare("UPDATE `contact` SET `trstatus` = 'clientCancelled' WHERE `id` = ?") or die $dbh->errstr;
			$sth->execute($contact_id) or die $sth->errstr;
			if ($sth->err) {
				my $err = 'UPDATE failed: ' . $sth->errstr;
				$blob->{resultCode} = 2400; # Command failed
				$blob->{human_readable_message} = 'Nu a fost Cancelled transferul cu success, ceva nu este in regula';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			else {
				# selectam datele despre starea contactului
				my ($crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
				my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
				my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");
				$blob->{id} = $identifier;
				$blob->{trStatus} = $trstatus;
				$blob->{reID} = $reid_identifier;
				$redate =~ s/\s/T/g;
				$redate .= '.0Z';
				$blob->{reDate} = $redate;
				$blob->{acID} = $acid_identifier;
				$acdate =~ s/\s/T/g;
				$acdate .= '.0Z';
				$blob->{acDate} = $acdate;
				$blob->{resultCode} = 1000; # Command completed successfully
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
			}
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
		}
		else {
			$blob->{resultCode} = 2301; # Object not pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the contact is NOT pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	#_________________________________________________________________________________________________________________
	elsif ($op eq 'query') {
		my ($crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
		if ($trstatus eq 'pending') {
			my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
			my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");
			$blob->{id} = $identifier;
			$blob->{trStatus} = $trstatus;
			$blob->{reID} = $reid_identifier;
			$redate =~ s/\s/T/g;
			$redate .= '.0Z';
			$blob->{reDate} = $redate;
			$blob->{acID} = $acid_identifier;
			$acdate =~ s/\s/T/g;
			$acdate .= '.0Z';
			$blob->{acDate} = $acdate;
			$blob->{resultCode} = 1000; # Command completed successfully
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
		else {
			$blob->{resultCode} = 2301; # Object not pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the contact is NOT pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	#_________________________________________________________________________________________________________________
	elsif ($op eq 'reject') {
		# doar CEL CARE PIERDE (Losing Registrar) poate sa aprobe sau sa rejecteze
		if ($registrar_id != $registrar_id_contact) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'Doar LOSING REGISTRAR poate sa rejecteze';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# -  A <contact:authInfo> element that contains authorization information associated with the contact object.
		# de revizuit
		if ($authInfo_pw) {
			my ($contact_authinfo_id) = $dbh->selectrow_array("SELECT `id` FROM `contact_authInfo` WHERE `contact_id` = '$contact_id' AND `authtype` = 'pw' AND `authinfo` = '$authInfo_pw' LIMIT 1");
			if (!$contact_authinfo_id) {
				$blob->{resultCode} = 2202; # Invalid authorization information
				$blob->{human_readable_message} = 'authInfo pw nu este corecta';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		my ($crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
		if ($trstatus eq 'pending') {
			# The losing registrar has five days once the contact is pending to respond.
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
			# totul ce e legat de reject facem aici
			my $sth = $dbh->prepare("UPDATE `contact` SET `trstatus` = 'clientRejected' WHERE `id` = ?") or die $dbh->errstr;
			$sth->execute($contact_id) or die $sth->errstr;
			if ($sth->err) {
				my $err = 'UPDATE failed: ' . $sth->errstr;
				$blob->{resultCode} = 2400; # Command failed
				$blob->{human_readable_message} = 'Nu a fost Rejected transferul cu success, ceva nu este in regula';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			else {
				# selectam datele despre starea contactului
				my ($crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
				my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
				my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");
				$blob->{id} = $identifier;
				$blob->{trStatus} = $trstatus;
				$blob->{reID} = $reid_identifier;
				$redate =~ s/\s/T/g;
				$redate .= '.0Z';
				$blob->{reDate} = $redate;
				$blob->{acID} = $acid_identifier;
				$acdate =~ s/\s/T/g;
				$acdate .= '.0Z';
				$blob->{acDate} = $acdate;
				$blob->{resultCode} = 1000; # Command completed successfully
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
			}
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
		}
		else {
			$blob->{resultCode} = 2301; # Object not pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the contact is NOT pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	#_________________________________________________________________________________________________________________
	elsif ($op eq 'request') {
		# The contact name must not be within 60 days of its initial registration or within 60 days of being transferred from another registrar. This is an ICANN regulation designed to reduce the incidence of fraudulent transactions.
		my ($days_from_registration) = $dbh->selectrow_array("SELECT DATEDIFF(CURRENT_TIMESTAMP,`crdate`) FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
		if ($days_from_registration < 60) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'The contact name must not be within 60 days of its initial registration';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		my ($last_trdate,$days_from_last_transfer) = $dbh->selectrow_array("SELECT `trdate`, DATEDIFF(CURRENT_TIMESTAMP,`trdate`) AS `intval` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
		if ($last_trdate) {
			if ($days_from_last_transfer < 60) {
				$blob->{resultCode} = 2201; # Authorization error
				$blob->{human_readable_message} = 'The contact name must not be within 60 days of its last transfer from another registrar';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		# -  A <contact:authInfo> element that contains authorization information associated with the contact object.
		my ($contact_authinfo_id) = $dbh->selectrow_array("SELECT `id` FROM `contact_authInfo` WHERE `contact_id` = '$contact_id' AND `authtype` = 'pw' AND `authinfo` = '$authInfo_pw' LIMIT 1");
		if (!$contact_authinfo_id) {
			$blob->{resultCode} = 2202; # Invalid authorization information
			$blob->{human_readable_message} = 'authInfo pw nu este corecta';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# The contact name must not be subject to any special locks or holds.
		my $sth = $dbh->prepare("SELECT `status` FROM `contact_status` WHERE `contact_id` = ?") or die $dbh->errstr;
		$sth->execute($contact_id) or die $sth->errstr;
		while (my ($status) = $sth->fetchrow_array()) {
			if (($status =~ m/.*(TransferProhibited)$/) || ($status =~ /^pending/)) {
				# This response code MUST be returned when a server receives a command to transform an object that cannot be completed due to server policy or business practices.
				$blob->{resultCode} = 2304; # Object status prohibits operation
				$blob->{human_readable_message} = 'Are un status care nu permite transferarea, mai intii schimba statutul apoi interpretarile EPP 5730 aici';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
		$sth->finish;

		if ($registrar_id == $registrar_id_contact) {
			# Response to a command Transfer Domain (with op:Request) whose execution fails because it has been submitted by the same Registrar who owns the contact.
			$blob->{resultCode} = 2106; # Object is not eligible for transfer
			$blob->{human_readable_message} = 'Destination client of the transfer operation is the contact sponsoring client';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		my ($crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
		if ((!$trstatus) || ($trstatus ne 'pending')) {
			# se insereaza dar fara data expirarii dupa procedura de transfer
			# For an inbound transfer, the contents of the <contact:reID> element will correspond to your registrar ID, and the contents of the <contact:acID> element will correspond to the losing registrar's ID. For an outbound transfer, the reverse is true.
			my $waiting_period = 5; # days
			my $sth = $dbh->prepare("UPDATE `contact` SET `trstatus` = 'pending', `reid` = '$registrar_id', `redate` = CURRENT_TIMESTAMP, `acid` = '$registrar_id_contact', `acdate` = DATE_ADD(CURRENT_TIMESTAMP, INTERVAL $waiting_period DAY) WHERE `id` = '$contact_id'") or die $dbh->errstr;
			$sth->execute() or die $sth->errstr;
			if ($sth->err) {
				my $err = 'UPDATE failed: ' . $sth->errstr;
				$blob->{resultCode} = 2400; # Command failed
				$blob->{human_readable_message} = 'Nu a fost initiat transferul cu success, ceva nu este in regula';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			else {
				# selectam datele despre starea contactului
				my ($crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
				my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
				my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");

				# The current sponsoring registrar will receive notification of a pending transfer.
				$dbh->do("INSERT INTO `poll` (`registrar_id`,`qdate`,`msg`,`msg_type`,`obj_name_or_id`,`obj_trStatus`,`obj_reID`,`obj_reDate`,`obj_acID`,`obj_acDate`,`obj_exDate`) VALUES('$registrar_id_contact',CURRENT_TIMESTAMP,'Transfer requested.','contactTransfer','$identifier','pending','$reid_identifier','$redate','$acid_identifier','$acdate',NULL)") or die $dbh->errstr;

				$blob->{id} = $identifier;
				$blob->{trStatus} = $trstatus;
				$blob->{reID} = $reid_identifier;
				$redate =~ s/\s/T/g;
				$redate .= '.0Z';
				$blob->{reDate} = $redate;
				$blob->{acID} = $acid_identifier;
				$acdate =~ s/\s/T/g;
				$acdate .= '.0Z';
				$blob->{acDate} = $acdate;
				$blob->{resultCode} = 1001; # Command completed successfully; action pending
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
			}
		}
		elsif ($trstatus eq 'pending') {
			# This response code MUST be returned when a server receives a command to transfer of an object that is pending transfer due to an earlier transfer request.
			$blob->{resultCode} = 2300; # Object pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the contact is pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	else {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Sunt acceptate doar op: approve|cancel|query|reject|request';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}
}
elsif ($obj = $xp->find('domain:transfer',$node)->get_node(0)) {
	################################################################
	#
	#			<transfer><domain:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-domain:transfer';
	$blob->{command} = 'transfer_domain';
	$blob->{obj_type} = 'domain';

	# -  A <domain:name> element that contains the fully qualified name of the domain object for which a transfer request is to be created, approved, rejected, or cancelled.
	my $name = $xp->findvalue('domain:name[1]', $obj);
	$blob->{obj_id} = $name;

	# -  An OPTIONAL <domain:authInfo> pentru op="query" si obligatoriu pentru celelalte valori ale op="approve|cancel|reject|request"
	my $authInfo_pw = $xp->findvalue('domain:authInfo/domain:pw[1]', $obj);
	my $authInfo_pw_roid = $xp->findvalue('domain:authInfo/domain:pw/@roid[1]', $obj);

	if (!$name) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Indica numele de domeniu';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$name = uc($name);
	my ($domain_id,$tldid,$registrar_id_domain) = $dbh->selectrow_array("SELECT `id`,`tldid`,`clid` FROM `domain` WHERE `name` = '$name' LIMIT 1");
	if (!$domain_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'Nu exista asa domeniu in registry';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# A server MAY automatically approve or reject all transfer requests that are not explicitly approved or rejected by the current sponsoring client within a fixed amount of time.
	# de obicei Registry le aproba automat daca nu sunt aprobate de Losing Registrar
	# if the transfer order is not cancelled/denied within 5 days, the Central Registry automatically transfers the domain name to the Gaining Registrar.
	#_________________________________________________________________________________________________________________
	if ($op eq 'approve') {
		# doar CEL CARE PIERDE (Losing Registrar) poate sa aprobe sau sa rejecteze
		if ($registrar_id != $registrar_id_domain) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'Doar LOSING REGISTRAR poate sa aprobe';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# -  A <domain:authInfo> element that contains authorization information associated with the domain object or authorization information associated with the domain object's registrant or associated contacts.
		# de revizuit
		if ($authInfo_pw) {
			my ($domain_authinfo_id) = $dbh->selectrow_array("SELECT `id` FROM `domain_authInfo` WHERE `domain_id` = '$domain_id' AND `authtype` = 'pw' AND `authinfo` = '$authInfo_pw' LIMIT 1");
			if (!$domain_authinfo_id) {
				$blob->{resultCode} = 2202; # Invalid authorization information
				$blob->{human_readable_message} = 'authInfo pw nu este corecta';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
		if ($trstatus eq 'pending') {
			# The losing registrar has five days once the domain is pending to respond.
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
			# totul ce e legat de aprove facem aici

			# aici facem o verificare daca are bani pe cont
			#_________________________________________________________________________________________________________________
			my $date_add = 0;
			my $price = 0;
			my ($registrar_balance,$creditLimit) = $dbh->selectrow_array("SELECT `accountBalance`,`creditLimit` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
			if ($transfer_exdate) {
				# aici o sa o calculam numarul de luni din diferenta dintre transfer_exdate - exdate
				($date_add) = $dbh->selectrow_array("SELECT PERIOD_DIFF(DATE_FORMAT(`transfer_exdate`, '%Y%m'), DATE_FORMAT(`exdate`, '%Y%m')) AS `intval` FROM `domain` WHERE `name` = '$name' LIMIT 1");
				($price) = $dbh->selectrow_array("SELECT `$date_add` FROM `domain_price` WHERE `tldid` = '$tldid' AND `command` = 'transfer' LIMIT 1");

				if (($registrar_balance + $creditLimit) < $price) {
					# This response code MUST be returned when a server attempts to execute a billable operation and the command cannot be completed due to a client-billing failure.
					$blob->{resultCode} = 2104; # Billing failure
					$blob->{human_readable_message} = 'Registrarul care a preluat acest domeniu nu are bani cu ce sa achite perioada de reinnoire care a rezultat in urma cererii de transfer';
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
			}
			#_________________________________________________________________________________________________________________

			my ($from) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
			my $sth = $dbh->prepare("UPDATE `domain` SET `exdate` = DATE_ADD(`exdate`, INTERVAL $date_add MONTH), `update` = CURRENT_TIMESTAMP, `clid` = '$reid', `upid` = '$registrar_id', `trdate` = CURRENT_TIMESTAMP, `trstatus` = 'clientApproved', `acdate` = CURRENT_TIMESTAMP, `transfer_exdate` = NULL, `rgpstatus` = 'transferPeriod', `transferPeriod` = '$date_add' WHERE `id` = '$domain_id'") or die $dbh->errstr;
			$sth->execute() or die $sth->errstr;

			$sth = $dbh->prepare("UPDATE `host` SET `clid` = '$reid', `upid` = '$registrar_id', `update` = CURRENT_TIMESTAMP, `trdate` = CURRENT_TIMESTAMP WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
			$sth->execute() or die $sth->errstr;

			if ($sth->err) {
				my $err = 'UPDATE failed: ' . $sth->errstr;
				$blob->{resultCode} = 2400; # Command failed
				$blob->{human_readable_message} = 'Nu a fost efectuat transferul cu success, ceva nu este in regula';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			else {
				#_________________________________________________________________________________________________________________
				$dbh->do("UPDATE `registrar` SET `accountBalance` = (`accountBalance` - $price) WHERE `id` = '$reid'") or die $dbh->errstr;
				$dbh->do("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES('$reid',CURRENT_TIMESTAMP,'transfer domain $name for period $date_add MONTH','-$price')") or die $dbh->errstr;
				#_________________________________________________________________________________________________________________

				my ($to) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
				$sth = $dbh->prepare("INSERT INTO `statement` (`registrar_id`,`date`,`command`,`domain_name`,`length_in_months`,`from`,`to`,`amount`) VALUES(?,CURRENT_TIMESTAMP,?,?,?,?,?,?)") or die $dbh->errstr;
				$sth->execute($reid,$blob->{cmd},$name,$date_add,$from,$to,$price) or die $sth->errstr;
				#_________________________________________________________________________________________________________________

				# selectam datele despre starea domeniului
				my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
				my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
				my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");

				my $curdate_id = $dbh->selectrow_array("SELECT `id` FROM `statistics` WHERE `date` = CURDATE()");
				if (!$curdate_id) {
					$dbh->do("INSERT IGNORE INTO `statistics` (`date`) VALUES(CURDATE())") or die $dbh->errstr;
				}
				$dbh->do("UPDATE `statistics` SET `transfered_domains` = `transfered_domains` + 1 WHERE `date` = CURDATE()") or die $dbh->errstr;

				$blob->{name} = $name;
				$blob->{trStatus} = $trstatus;
				$blob->{reID} = $reid_identifier;
				$redate =~ s/\s/T/g;
				$redate .= '.0Z';
				$blob->{reDate} = $redate;
				$blob->{acID} = $acid_identifier;
				$acdate =~ s/\s/T/g;
				$acdate .= '.0Z';
				$blob->{acDate} = $acdate;
				if ($transfer_exdate) {
					$transfer_exdate =~ s/\s/T/g;
					$transfer_exdate .= '.0Z';
					$blob->{exDate} = $transfer_exdate;
				}
				$blob->{resultCode} = 1000; # Command completed successfully
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
			}
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
		}
		else {
			$blob->{resultCode} = 2301; # Object not pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the domain is NOT pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	#_________________________________________________________________________________________________________________
	elsif ($op eq 'cancel') {
		# doar SOLICITANTUL (Requesting or 'Gaining' Registrar) poate face cancel
		if ($registrar_id == $registrar_id_domain) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'Doar SOLICITANTUL poate face cancel';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# -  A <domain:authInfo> element that contains authorization information associated with the domain object or authorization information associated with the domain object's registrant or associated contacts.
		# de revizuit
		if ($authInfo_pw) {
			my ($domain_authinfo_id) = $dbh->selectrow_array("SELECT `id` FROM `domain_authInfo` WHERE `domain_id` = '$domain_id' AND `authtype` = 'pw' AND `authinfo` = '$authInfo_pw' LIMIT 1");
			if (!$domain_authinfo_id) {
				$blob->{resultCode} = 2202; # Invalid authorization information
				$blob->{human_readable_message} = 'authInfo pw nu este corecta';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
		if ($trstatus eq 'pending') {
			# The losing registrar has five days once the domain is pending to respond.
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
			# totul ce e legat de cancel facem aici
			my $sth = $dbh->prepare("UPDATE `domain` SET `trstatus` = 'clientCancelled' WHERE `id` = '$domain_id'") or die $dbh->errstr;
			$sth->execute() or die $sth->errstr;
			if ($sth->err) {
				my $err = 'UPDATE failed: ' . $sth->errstr;
				$blob->{resultCode} = 2400; # Command failed
				$blob->{human_readable_message} = 'Nu a fost Cancelled transferul cu success, ceva nu este in regula';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			else {
				# selectam datele despre starea domeniului
				my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
				my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
				my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");
				$blob->{name} = $name;
				$blob->{trStatus} = $trstatus;
				$blob->{reID} = $reid_identifier;
				$redate =~ s/\s/T/g;
				$redate .= '.0Z';
				$blob->{reDate} = $redate;
				$blob->{acID} = $acid_identifier;
				$acdate =~ s/\s/T/g;
				$acdate .= '.0Z';
				$blob->{acDate} = $acdate;
				if ($transfer_exdate) {
					$transfer_exdate =~ s/\s/T/g;
					$transfer_exdate .= '.0Z';
					$blob->{exDate} = $transfer_exdate;
				}
				$blob->{resultCode} = 1000; # Command completed successfully
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
			}
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
		}
		else {
			$blob->{resultCode} = 2301; # Object not pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the domain is NOT pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	#_________________________________________________________________________________________________________________
	elsif ($op eq 'query') {
		my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
		if ($trstatus eq 'pending') {
			my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
			my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");
			$blob->{name} = $name;
			$blob->{trStatus} = $trstatus;
			$blob->{reID} = $reid_identifier;
			$redate =~ s/\s/T/g;
			$redate .= '.0Z';
			$blob->{reDate} = $redate;
			$blob->{acID} = $acid_identifier;
			$acdate =~ s/\s/T/g;
			$acdate .= '.0Z';
			$blob->{acDate} = $acdate;
			# -  An OPTIONAL <domain:exDate> element that contains the end of the domain object's validity period if the <transfer> command caused or causes a change in the validity period.
			if ($transfer_exdate) {
				$transfer_exdate =~ s/\s/T/g;
				$transfer_exdate .= '.0Z';
				$blob->{exDate} = $transfer_exdate;
			}
			$blob->{resultCode} = 1000; # Command completed successfully
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
		else {
			$blob->{resultCode} = 2301; # Object not pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the domain is NOT pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	#_________________________________________________________________________________________________________________
	elsif ($op eq 'reject') {
		# doar CEL CARE PIERDE (Losing Registrar) poate sa aprobe sau sa rejecteze
		if ($registrar_id != $registrar_id_domain) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'Doar LOSING REGISTRAR poate sa rejecteze';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# -  A <domain:authInfo> element that contains authorization information associated with the domain object or authorization information associated with the domain object's registrant or associated contacts.
		# de revizuit
		if ($authInfo_pw) {
			my ($domain_authinfo_id) = $dbh->selectrow_array("SELECT `id` FROM `domain_authInfo` WHERE `domain_id` = '$domain_id' AND `authtype` = 'pw' AND `authinfo` = '$authInfo_pw' LIMIT 1");
			if (!$domain_authinfo_id) {
				$blob->{resultCode} = 2202; # Invalid authorization information
				$blob->{human_readable_message} = 'authInfo pw nu este corecta';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
		if ($trstatus eq 'pending') {
			# The losing registrar has five days once the domain is pending to respond.
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
			# totul ce e legat de reject facem aici
			my $sth = $dbh->prepare("UPDATE `domain` SET `trstatus` = ? WHERE `id` = ?") or die $dbh->errstr;
			$sth->execute('clientRejected',$domain_id) or die $sth->errstr;
			if ($sth->err) {
				my $err = 'UPDATE failed: ' . $sth->errstr;
				$blob->{resultCode} = 2400; # Command failed
				$blob->{human_readable_message} = 'Nu a fost Rejected transferul cu success, ceva nu este in regula';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
			else {
				# selectam datele despre starea domeniului
				my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
				my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
				my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");
				$blob->{name} = $name;
				$blob->{trStatus} = $trstatus;
				$blob->{reID} = $reid_identifier;
				$redate =~ s/\s/T/g;
				$redate .= '.0Z';
				$blob->{reDate} = $redate;
				$blob->{acID} = $acid_identifier;
				$acdate =~ s/\s/T/g;
				$acdate .= '.0Z';
				$blob->{acDate} = $acdate;
				if ($transfer_exdate) {
					$transfer_exdate =~ s/\s/T/g;
					$transfer_exdate .= '.0Z';
					$blob->{exDate} = $transfer_exdate;
				}
				$blob->{resultCode} = 1000; # Command completed successfully
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
			}
			# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
		}
		else {
			$blob->{resultCode} = 2301; # Object not pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the domain is NOT pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	#_________________________________________________________________________________________________________________
	elsif ($op eq 'request') {
		# The domain name must not be within 60 days of its initial registration or within 60 days of being transferred from another registrar. This is an ICANN regulation designed to reduce the incidence of fraudulent transactions.
		my ($days_from_registration) = $dbh->selectrow_array("SELECT DATEDIFF(CURRENT_TIMESTAMP,`crdate`) FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
		if ($days_from_registration < 60) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'The domain name must not be within 60 days of its initial registration';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		my ($last_trdate,$days_from_last_transfer) = $dbh->selectrow_array("SELECT `trdate`, DATEDIFF(CURRENT_TIMESTAMP,`trdate`) AS `intval` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
		if ($last_trdate) {
			if ($days_from_last_transfer < 60) {
				$blob->{resultCode} = 2201; # Authorization error
				$blob->{human_readable_message} = 'The domain name must not be within 60 days of its last transfer from another registrar';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		# The domain name must not be more than 30 days past its expiry date.
		my ($days_from_expiry_date) = $dbh->selectrow_array("SELECT DATEDIFF(CURRENT_TIMESTAMP,`exdate`) FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
		if ($days_from_expiry_date > 30) {
			$blob->{resultCode} = 2201; # Authorization error
			$blob->{human_readable_message} = 'The domain name must not be more than 30 days past its expiry date.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# -  A <domain:authInfo> element that contains authorization information associated with the domain object or authorization information associated with the domain object's registrant or associated contacts.
		if ($authInfo_pw_roid) {
			# eliminam orice simbol din roid si pastram doar cifrele C_1234-$c{'repository'}
			$authInfo_pw_roid =~ s/\D//g;
			my ($contact_id_roid) = $dbh->selectrow_array("SELECT `contact_id` FROM `domain_contact_map` WHERE `domain_id` = '$domain_id' AND `contact_id` = '$authInfo_pw_roid' LIMIT 1");
			if (!$contact_id_roid) {
				$blob->{resultCode} = 2202; # Invalid authorization information
				$blob->{human_readable_message} = 'authInfo pw cu roid este invalid nu este asa ROID';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}

			my ($contact_authInfo_id) = $dbh->selectrow_array("SELECT `id` FROM `contact_authInfo` WHERE `contact_id` = '$authInfo_pw_roid' AND `authtype` = 'pw'  AND `authinfo` = '$authInfo_pw' LIMIT 1");

			if (!$contact_authInfo_id) {
				$blob->{resultCode} = 2202; # Invalid authorization information
				$blob->{human_readable_message} = 'authInfo pw cu roid este invalid aici totul va fi revizuit';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
		else {
			my ($domain_authinfo_id) = $dbh->selectrow_array("SELECT `id` FROM `domain_authInfo` WHERE `domain_id` = '$domain_id' AND `authtype` = 'pw' AND `authinfo` = '$authInfo_pw' LIMIT 1");
			if (!$domain_authinfo_id) {
				$blob->{resultCode} = 2202; # Invalid authorization information
				$blob->{human_readable_message} = 'authInfo pw nu este corecta';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}

		# The domain name must not be subject to any special locks or holds.
		my $sth = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
		$sth->execute($domain_id) or die $sth->errstr;
		while (my ($status) = $sth->fetchrow_array()) {
			if (($status =~ m/.*(TransferProhibited)$/) || ($status =~ /^pending/)) {
				# This response code MUST be returned when a server receives a command to transform an object that cannot be completed due to server policy or business practices.
				$blob->{resultCode} = 2304; # Object status prohibits operation
				$blob->{human_readable_message} = 'Are un status care nu permite transferarea, mai intii schimba statutul apoi interpretarile EPP 5730 aici';
				my $msg = epp_writer($blob);
				print $msg;
				my $uptr = update_transaction($msg);
				exit;
			}
		}
		$sth->finish;

		if ($registrar_id == $registrar_id_domain) {
			# Response to a command Transfer Domain (with op:Request) whose execution fails because it has been submitted by the same Registrar who owns the domain.
			$blob->{resultCode} = 2106; # Object is not eligible for transfer
			$blob->{human_readable_message} = 'Destination client of the transfer operation is the domain sponsoring client';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
		if ((!$trstatus) || ($trstatus ne 'pending')) {
			# daca clientul a introdus si <domain:period> atunci facem validarea daca este totul corect
			my $period = $xp->findvalue('domain:period[1]', $obj)->value; # 1-99
			my $period_unit = $xp->findvalue('domain:period/@unit[1]', $obj); # m|y
			if ($period) {
				if (($period < 1) || ($period > 99)) {
					# This response code MUST be returned when a server receives a command parameter whose value is outside the range of values specified by the protocol.
					$blob->{resultCode} = 2004; # Parameter value range error
					$blob->{human_readable_message} = "domain:period minLength value='1', maxLength value='99'";
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

			if ($period_unit) {
				if ($period_unit !~ /^(m|y)$/) {
					# This response code MUST be returned when a server receives a command parameter whose value is outside the range of values specified by the protocol.
					$blob->{resultCode} = 2004; # Parameter value range error
					$blob->{human_readable_message} = "domain:period unit m|y";
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
			}

			my $date_add = 0;
			if ($period_unit eq 'y') {
				$date_add = ($period * 12);
			}
			elsif ($period_unit eq 'm') {
				$date_add = $period;
			}
			else {
				$date_add = 0;
			}

			if ($date_add > 0) {
				# The number of units available MAY be subject to limits imposed by the server.
				# de avut in vedere ca unii registrari nu accepta transfer cu renew pe perioada de 10 ani, altii nici chiar cu 5 ani
				# 1 year 2 years 3 years 5 years 10 years 
				if ($date_add !~ /^(12|24|36|48|60|72|84|96|108|120)$/) {
					$blob->{resultCode} = 2306; # Parameter value policy error
					$blob->{human_readable_message} = 'Sa nu fie mai mic de 1 an si nu mai mare de 10';
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

				# aici facem o verificare daca are bani pe cont acel registrar care a solicitat transferul
				my ($registrar_balance,$creditLimit) = $dbh->selectrow_array("SELECT `accountBalance`,`creditLimit` FROM `registrar` WHERE `id` = '$registrar_id' LIMIT 1");
				my ($price) = $dbh->selectrow_array("SELECT `$date_add` FROM `domain_price` WHERE `tldid` = '$tldid' AND `command` = 'transfer' LIMIT 1");

				if (($registrar_balance + $creditLimit) < $price) {
					# This response code MUST be returned when a server attempts to execute a billable operation and the command cannot be completed due to a client-billing failure.
					$blob->{resultCode} = 2104; # Billing failure
					$blob->{human_readable_message} = 'Registrarul care vrea sa preea acest domeniu nu are bani cu ce sa achite.';
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}

				# se insereaza cu data expirarii dupa procedura de transfer
				# For an inbound transfer, the contents of the <domain:reID> element will correspond to your registrar ID, and the contents of the <domain:acID> element will correspond to the losing registrar's ID. For an outbound transfer, the reverse is true.
				my $waiting_period = 5; # days
				$sth = $dbh->prepare("UPDATE `domain` SET `trstatus` = 'pending', `reid` = '$registrar_id', `redate` = CURRENT_TIMESTAMP, `acid` = '$registrar_id_domain', `acdate` = DATE_ADD(CURRENT_TIMESTAMP, INTERVAL $waiting_period DAY), `transfer_exdate` = DATE_ADD(`exdate`, INTERVAL $date_add MONTH) WHERE `id` = '$domain_id'") or die $dbh->errstr;
				$sth->execute() or die $sth->errstr;
				if ($sth->err) {
					my $err = 'UPDATE failed: ' . $sth->errstr;
					$blob->{resultCode} = 2400; # Command failed
					$blob->{human_readable_message} = 'Nu a fost initiat transferul cu success, ceva nu este in regula';
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
				else {
					# selectam datele despre starea domeniului
					my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
					my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
					my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");

					# The current sponsoring registrar will receive notification of a pending transfer.
					$dbh->do("INSERT INTO `poll` (`registrar_id`,`qdate`,`msg`,`msg_type`,`obj_name_or_id`,`obj_trStatus`,`obj_reID`,`obj_reDate`,`obj_acID`,`obj_acDate`,`obj_exDate`) VALUES('$registrar_id_domain',CURRENT_TIMESTAMP,'Transfer requested.','domainTransfer','$name','pending','$reid_identifier','$redate','$acid_identifier','$acdate','$transfer_exdate')") or die $dbh->errstr;

					$blob->{name} = $name;
					$blob->{trStatus} = $trstatus;
					$blob->{reID} = $reid_identifier;
					$redate =~ s/\s/T/g;
					$redate .= '.0Z';
					$blob->{reDate} = $redate;
					$blob->{acID} = $acid_identifier;
					$acdate =~ s/\s/T/g;
					$acdate .= '.0Z';
					$blob->{acDate} = $acdate;
					$transfer_exdate =~ s/\s/T/g;
					$transfer_exdate .= '.0Z';
					$blob->{exDate} = $transfer_exdate;
					$blob->{resultCode} = 1001; # Command completed successfully; action pending
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
				}
			}
			else {
				# se insereaza dar fara data expirarii dupa procedura de transfer
				# For an inbound transfer, the contents of the <domain:reID> element will correspond to your registrar ID, and the contents of the <domain:acID> element will correspond to the losing registrar's ID. For an outbound transfer, the reverse is true.
				my $waiting_period = 5; # days
				my $sth = $dbh->prepare("UPDATE `domain` SET `trstatus` = 'pending', `reid` = '$registrar_id', `redate` = CURRENT_TIMESTAMP, `acid` = '$registrar_id_domain', `acdate` = DATE_ADD(CURRENT_TIMESTAMP, INTERVAL $waiting_period DAY), `transfer_exdate` = NULL WHERE `id` = '$domain_id'") or die $dbh->errstr;
				$sth->execute() or die $sth->errstr;
				if ($sth->err) {
					my $err = 'UPDATE failed: ' . $sth->errstr;
					$blob->{resultCode} = 2400; # Command failed
					$blob->{human_readable_message} = 'Nu a fost initiat transferul cu success, ceva nu este in regula';
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
					exit;
				}
				else {
					# selectam datele despre starea domeniului
					my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
					my ($reid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$reid' LIMIT 1");
					my ($acid_identifier) = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$acid' LIMIT 1");

					# The current sponsoring registrar will receive notification of a pending transfer.
					$dbh->do("INSERT INTO `poll` (`registrar_id`,`qdate`,`msg`,`msg_type`,`obj_name_or_id`,`obj_trStatus`,`obj_reID`,`obj_reDate`,`obj_acID`,`obj_acDate`,`obj_exDate`) VALUES('$registrar_id_domain',CURRENT_TIMESTAMP,'Transfer requested.','domainTransfer','$name','pending','$reid_identifier','$redate','$acid_identifier','$acdate',NULL)") or die $dbh->errstr;

					$blob->{name} = $name;
					$blob->{trStatus} = $trstatus;
					$blob->{reID} = $reid_identifier;
					$redate =~ s/\s/T/g;
					$redate .= '.0Z';
					$blob->{reDate} = $redate;
					$blob->{acID} = $acid_identifier;
					$acdate =~ s/\s/T/g;
					$acdate .= '.0Z';
					$blob->{acDate} = $acdate;
					$blob->{resultCode} = 1001; # Command completed successfully; action pending
					my $msg = epp_writer($blob);
					print $msg;
					my $uptr = update_transaction($msg);
				}
			}
		}
		elsif ($trstatus eq 'pending') {
			# This response code MUST be returned when a server receives a command to transfer of an object that is pending transfer due to an earlier transfer request.
			$blob->{resultCode} = 2300; # Object pending transfer
			$blob->{human_readable_message} = 'Response to a command whose execution fails because the domain is pending transfer.';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	else {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = 'Sunt acceptate doar op: approve|cancel|query|reject|request';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}
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