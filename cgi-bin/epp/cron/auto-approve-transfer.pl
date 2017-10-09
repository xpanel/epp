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
use DBI;
use EPP::Date qw(:all);
use vars qw(%c $dbh);
*c = \%EPP::Config::c;
$dbh = DBI->connect("DBI:mysql:$c{'mysql_database'}:$c{'mysql_host'}:$c{'mysql_port'}","$c{'mysql_username'}","$c{'mysql_password'}") or die "$DBI::errstr";

my $sth_domain = $dbh->prepare("SELECT `id`,`name`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE CURRENT_TIMESTAMP > `acdate` AND `trstatus` = 'pending'");
$sth_domain->execute();
while (my ($domain_id,$name,$registrant,$crdate,$exdate,$update,$clid,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $sth_domain->fetchrow_array) {

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

		# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 
		# selectam din cimpul tld, le facem cu litere mari apoi le comparam
		my ($label,$domain_extension) = $name =~ /^([^\.]+)\.(.+)$/;
		my $tld_id;
		my $sth_tld = $dbh->prepare("SELECT `id`,`tld` FROM `domain_tld`") or die $dbh->errstr;
		$sth_tld->execute() or die $sth_tld->errstr;
		while (my ($id,$tld) = $sth_tld->fetchrow_array()) {
			$tld = uc($tld);
			my $ext = '.'.$domain_extension;
			if ($ext eq $tld) {
				$tld_id = $id;
				last;
			}
		}
		$sth_tld->finish;
		# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 

		($price) = $dbh->selectrow_array("SELECT `m$date_add` FROM `domain_price` WHERE `tldid` = '$tld_id' AND `command` = 'transfer' LIMIT 1");

		if (($registrar_balance + $creditLimit) < $price) {
			# This response code MUST be returned when a server attempts to execute a billable operation and the command cannot be completed due to a client-billing failure.
			# resultCode = 2104; # Billing failure
			my $echo = 'Registrarul care a preluat acest domeniu nu are bani cu ce sa achite perioada de reinnoire care a rezultat in urma cererii de transfer';
			`echo '$name - $echo' >>/var/log/epp/domain_auto_approve_transfer.log`;
			next;
		}
	}
	#_________________________________________________________________________________________________________________

	my ($from) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
	my $sth_update = $dbh->prepare("UPDATE `domain` SET `exdate` = DATE_ADD(`exdate`, INTERVAL $date_add MONTH), `update` = CURRENT_TIMESTAMP, `clid` = '$reid', `upid` = '$clid', `trdate` = CURRENT_TIMESTAMP, `trstatus` = 'serverApproved', `acdate` = CURRENT_TIMESTAMP, `transfer_exdate` = NULL WHERE `id` = '$domain_id'") or die $dbh->errstr;
	$sth_update->execute() or die $sth_update->errstr;

	my $sth_update_host = $dbh->prepare("UPDATE `host` SET `clid` = '$reid', `upid` = NULL, `update` = CURRENT_TIMESTAMP, `trdate` = CURRENT_TIMESTAMP WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
	$sth_update_host->execute() or die $sth_update_host->errstr;

	if ($sth_update->err) {
		my $err = 'UPDATE failed: ' . $sth_update->errstr;
		# resultCode = 2400; # Command failed
		my $echo = "Nu a fost efectuat transferul cu success, ceva nu este in regula | $err";
		`echo '$name - $echo' >>/var/log/epp/domain_auto_approve_transfer.log`;
		next;
	}
	else {
		#_________________________________________________________________________________________________________________
		$dbh->do("UPDATE `registrar` SET `accountBalance` = (`accountBalance` - $price) WHERE `id` = '$reid'") or die $dbh->errstr;
		$dbh->do("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES('$reid',CURRENT_TIMESTAMP,'transfer domain $name for period $date_add MONTH','-$price')") or die $dbh->errstr;
		#_________________________________________________________________________________________________________________

		my ($to) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
		my $sth_insert_statement = $dbh->prepare("INSERT INTO `statement` (`registrar_id`,`date`,`command`,`domain_name`,`length_in_months`,`from`,`to`,`amount`) VALUES(?,CURRENT_TIMESTAMP,?,?,?,?,?,?)") or die $dbh->errstr;
		$sth_insert_statement->execute($reid,'transfer',$name,$date_add,$from,$to,$price) or die $sth_insert_statement->errstr;
		#_________________________________________________________________________________________________________________

		# selectam datele despre starea domeniului
		my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");
		#_________________________________________________________________________________________________________________
		my $sth_auto_approve_transfer = $dbh->prepare("INSERT INTO `domain_auto_approve_transfer` (`name`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`transfer_exdate`) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)") or die $dbh->errstr;
		$sth_auto_approve_transfer->execute($name,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid || undef,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$transfer_exdate || undef) or die $sth_auto_approve_transfer->errstr;
		#_________________________________________________________________________________________________________________
	}
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

}
$sth_domain->finish;




my $sth_contact = $dbh->prepare("SELECT `id`,`crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE CURRENT_TIMESTAMP > `acdate` AND `trstatus` = 'pending'");
$sth_contact->execute();
while (my ($contact_id,$crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $sth_contact->fetchrow_array) {

	# The losing registrar has five days once the contact is pending to respond.
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# totul ce e legat de aprove facem aici

	my $sth_update_contact = $dbh->prepare("UPDATE `contact` SET `update` = CURRENT_TIMESTAMP, `clid` = '$reid', `upid` = NULL, `trdate` = CURRENT_TIMESTAMP, `trstatus` = 'serverApproved', `acdate` = CURRENT_TIMESTAMP WHERE `id` = ?") or die $dbh->errstr;
	$sth_update_contact->execute($contact_id) or die $sth_update_contact->errstr;

	if ($sth_update_contact->err) {
		my $err = 'UPDATE failed: ' . $sth_update_contact->errstr;
		# resultCode = 2400; # Command failed
		my $echo = "Nu a fost efectuat transferul cu success, ceva nu este in regula | $err";
		`echo '$contact_id - $echo' >>/var/log/epp/contact_auto_approve_transfer.log`;
		next;
	}
	else {
		# selectam datele despre starea contactului
		my ($identifier,$crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) = $dbh->selectrow_array("SELECT `identifier`,`crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
		#_________________________________________________________________________________________________________________
		my $sth_auto_approve_transfer = $dbh->prepare("INSERT INTO `contact_auto_approve_transfer` (`identifier`,`crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`) VALUES(?,?,?,?,?,?,?,?,?,?,?)") or die $dbh->errstr;
		$sth_auto_approve_transfer->execute($identifier,$crid,$crdate,$upid || undef,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate) or die $sth_auto_approve_transfer->errstr;
		#_________________________________________________________________________________________________________________
	}
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
}
$sth_contact->finish;


# A server MAY automatically approve or reject all transfer requests that are not explicitly approved or rejected by the current sponsoring client 
# within a fixed amount of time.

# A registrant goes to a new registrar with their domain. Maybe the new registrar has a better package deal with better prices?

# The registrant provides the auth info to the registrar.

# The registrar issues a transfer request, with an optional renewal period. If the auth info provided was invalid, then the transfer request will fail. 
#(A transfer "query" could have told the registrar this, but why perform in two requests to the registry what you can accomplish with a single request?)

# If the request was successful, the current sponsoring registrar receives notification that a domain of theirs is being transfered away.

# Depending on registry policy, the losing registrar might have a couple of days to proactively approve or reject the transfer. 
# The requesting registrar also has a chance to cancel the transfer request during this time.

# If the losing registrar takes no action, the registry will likely automatically approve or reject the transfer depending on their policies. 
# Most will usually auto-approve transfers.

# The gaining registrar should receive notification of the results of the transfer. If the transfer is successful, the gaining registrar will be charged
# for the renewal period of the domain. If none was specified in the request, the registry usually assigns a default (often 1 year). 

# The pending-transfer period is 5 days.  If the transfer request is neither approved nor rejected by the losing Registrar within the 5 day pending-transfer period,
# VeriSign will automatically approve the request.