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
use DBI;
use POSIX 'strftime';
use vars qw(%c $dbh);
*c = \%EPP::Config::c;

$dbh = DBI->connect("DBI:mysql:$c{'mysql_database'}:$c{'mysql_host'}:$c{'mysql_port'}","$c{'mysql_username'}","$c{'mysql_password'}") or die "$DBI::errstr";

my $auto_renew = 0;
if ($auto_renew) {
	# The current value of the Auto-Renew Grace Period is 45 calendar days.
	my $sth_autorenewperiod = $dbh->prepare("SELECT `id`,`name`,`tldid`,`exdate`,`clid` FROM `domain` WHERE CURRENT_TIMESTAMP > `exdate` AND `rgpstatus` IS NULL") or die $dbh->errstr;
	$sth_autorenewperiod->execute() or die $sth_autorenewperiod->errstr;

	while (my ($domain_id,$name,$tldid,$exdate,$clid) = $sth_autorenewperiod->fetchrow_array) {
		my $sth_status = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
		$sth_status->execute($domain_id) or die $sth_status->errstr;

		my $set_autorenewPeriod = 1;

		while (my ($status) = $sth_status->fetchrow_array()) {
			if (($status =~ m/.*(serverUpdateProhibited|serverDeleteProhibited)$/) || ($status =~ /^pending/)) {
				$set_autorenewPeriod = 0;
				next;
			}
		}
		$sth_status->finish;

		if ($set_autorenewPeriod) {
			# aici o matematica daca are bani pentru autoRenew
			#_________________________________________________________________________________________________________________
			my ($registrar_balance,$creditLimit) = $dbh->selectrow_array("SELECT `accountBalance`,`creditLimit` FROM `registrar` WHERE `id` = '$clid' LIMIT 1");
			my $price = $dbh->selectrow_array("SELECT `12` FROM `domain_price` WHERE `tldid` = '$tldid' AND `command` = 'renew' LIMIT 1");

			if (($registrar_balance + $creditLimit) > $price) {
				#_________________________________________________________________________________________________________________
				$dbh->do("UPDATE `domain` SET `rgpstatus` = 'autoRenewPeriod', `exdate` = DATE_ADD(`exdate`, INTERVAL 12 MONTH), `autoRenewPeriod` = '12', `renewedDate` = `exdate` WHERE `id` = '$domain_id'") or die $dbh->errstr;

				#_________________________________________________________________________________________________________________
				$dbh->do("UPDATE `registrar` SET `accountBalance` = (`accountBalance` - $price) WHERE `id` = '$clid'") or die $dbh->errstr;
				$dbh->do("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES('$clid',CURRENT_TIMESTAMP,'autoRenew domain $name for period 12 MONTH','-$price')") or die $dbh->errstr;

				#_________________________________________________________________________________________________________________
				my ($to) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
				my $sth = $dbh->prepare("INSERT INTO `statement` (`registrar_id`,`date`,`command`,`domain_name`,`length_in_months`,`from`,`to`,`amount`) VALUES(?,CURRENT_TIMESTAMP,?,?,?,?,?,?)") or die $dbh->errstr;
				$sth->execute($clid,'autoRenew',$name,'12',$exdate,$to,$price) or die $sth->errstr;

				#_________________________________________________________________________________________________________________
				my $curdate_id = $dbh->selectrow_array("SELECT `id` FROM `statistics` WHERE `date` = CURDATE()");
				if (!$curdate_id) {
					$dbh->do("INSERT IGNORE INTO `statistics` (`date`) VALUES(CURDATE())") or die $dbh->errstr;
				}
				$dbh->do("UPDATE `statistics` SET `renewed_domains` = `renewed_domains` + 1 WHERE `date` = CURDATE()") or die $dbh->errstr;
			}
			else {
				# nu au bani il trimitem la stergere
				$dbh->do("DELETE FROM `domain_status` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
				$dbh->do("UPDATE `domain` SET `rgpstatus` = 'redemptionPeriod', `delTime` = `exdate` WHERE `id` = '$domain_id'") or die $dbh->errstr;
				$dbh->do("INSERT INTO `domain_status` (`domain_id`,`status`) VALUES('$domain_id','pendingDelete')") or die $dbh->errstr;
			}
			#_________________________________________________________________________________________________________________
		}

	print strftime("%Y-%m-%d %H:%M:%S", localtime);
	print " - $domain_id\t|\t$name\t|\trgpStatus:autoRenewPeriod exdate:$exdate";
	print "\n";
	}
	$sth_autorenewperiod->finish;
}
else {
	my $grace_period = 30;

	# We currently endeavor to provide a grace period that extends 30 days past the expiration date, to allow the renewal of domain name registration services.
	# During this period a customer can renew a domain name registration; however, a grace period is not guaranteed and can change or be eliminated at any time without notice.
	# Consequently, every customer who desires to renew his or her domain name registration services should do so in advance of the expiration date to avoid any unintended domain name deletion.
	my $sth_graceperiod = $dbh->prepare("SELECT `id`,`name`,`exdate` FROM `domain` WHERE CURRENT_TIMESTAMP > DATE_ADD(`exdate`, INTERVAL $grace_period DAY) AND `rgpstatus` IS NULL") or die $dbh->errstr;
	$sth_graceperiod->execute() or die $sth_graceperiod->errstr;

	while (my ($domain_id,$name,$exdate) = $sth_graceperiod->fetchrow_array) {
		my $sth_status = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
		$sth_status->execute($domain_id) or die $sth_status->errstr;

		my $set_graceperiod = 1;

		while (my ($status) = $sth_status->fetchrow_array()) {
			if (($status =~ m/.*(serverUpdateProhibited|serverDeleteProhibited)$/) || ($status =~ /^pending/)) {
				$set_graceperiod = 0;
				next;
			}
		}
		$sth_status->finish;

		if ($set_graceperiod) {
			$dbh->do("DELETE FROM `domain_status` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
			$dbh->do("UPDATE `domain` SET `rgpstatus` = 'redemptionPeriod', `delTime` = DATE_ADD(`exdate`, INTERVAL $grace_period DAY) WHERE `id` = '$domain_id'") or die $dbh->errstr;
			$dbh->do("INSERT INTO `domain_status` (`domain_id`,`status`) VALUES('$domain_id','pendingDelete')") or die $dbh->errstr;
		}

	print strftime("%Y-%m-%d %H:%M:%S", localtime);
	print " - $domain_id\t|\t$name\t|\trgpStatus:redemptionPeriod exdate:$exdate";
	print "\n";
	}
	$sth_graceperiod->finish;
}





# clean autoRenewPeriod after 45 days _________________________________________________________________________________________________________________
$dbh->do("UPDATE `domain` SET `rgpstatus` = NULL WHERE CURRENT_TIMESTAMP > DATE_ADD(`exdate`, INTERVAL 45 DAY) AND `rgpstatus` = 'autoRenewPeriod'") or die $dbh->errstr;
$dbh->do("UPDATE `domain` SET `rgpstatus` = NULL WHERE CURRENT_TIMESTAMP > DATE_ADD(`crdate`, INTERVAL 5 DAY) AND `rgpstatus` = 'addPeriod'") or die $dbh->errstr;
$dbh->do("UPDATE `domain` SET `rgpstatus` = NULL WHERE CURRENT_TIMESTAMP > DATE_ADD(`renewedDate`, INTERVAL 5 DAY) AND `rgpstatus` = 'renewPeriod'") or die $dbh->errstr;
$dbh->do("UPDATE `domain` SET `rgpstatus` = NULL WHERE CURRENT_TIMESTAMP > DATE_ADD(`trdate`, INTERVAL 5 DAY) AND `rgpstatus` = 'transferPeriod'") or die $dbh->errstr;





# The current value of the redemptionPeriod is 30 calendar days.
my $sth_pendingdelete = $dbh->prepare("SELECT `id`,`name`,`exdate` FROM `domain` WHERE CURRENT_TIMESTAMP > DATE_ADD(`delTime`, INTERVAL 30 DAY) AND `rgpstatus` = 'redemptionPeriod'") or die $dbh->errstr;
$sth_pendingdelete->execute() or die $sth_pendingdelete->errstr;

while (my ($domain_id,$name,$exdate) = $sth_pendingdelete->fetchrow_array) {
	my $sth_status = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
	$sth_status->execute($domain_id) or die $sth_status->errstr;

	my $set_pendingDelete = 1;

	while (my ($status) = $sth_status->fetchrow_array()) {
		if ($status =~ m/.*(serverUpdateProhibited|serverDeleteProhibited)$/) {
			$set_pendingDelete = 0;
			next;
		}
	}
	$sth_status->finish;

	if ($set_pendingDelete) {
		$dbh->do("UPDATE `domain` SET `rgpstatus` = 'pendingDelete' WHERE `id` = '$domain_id'") or die $dbh->errstr;
	}

print strftime("%Y-%m-%d %H:%M:%S", localtime);
print " - $domain_id\t|\t$name\t|\trgpStatus:pendingDelete exdate:$exdate";
print "\n";
}
$sth_pendingdelete->finish;









# If the registrar fails to submit restoration documentation within the seven calendar days, the domain name is sent back to redemption period status.

# A domain name is placed in PENDINGRESTORE status when a registrar requests restoration of a domain that is in REDEMPTIONPERIOD status.
# A name that is in PENDINGRESTORE status will be included in the zone file.
# Registrar requests to modify or otherwise update a domain in REDEMPTIONPERIOD status will be rejected.
# A domain name is returned to REDEMPTIONPERIOD status a specified number of calendar days after it is placed in PENDINGRESTORE
# unless the registrar submits a complete Registrar Restore Report to the Registry Operator. The current length of this Pending Restore Period is seven calendar days.
my $sth_pendingRestore = $dbh->prepare("SELECT `id`,`name`,`exdate` FROM `domain` WHERE `rgpstatus` = 'pendingRestore' AND (CURRENT_TIMESTAMP > DATE_ADD(`resTime`, INTERVAL 7 DAY))") or die $dbh->errstr;
$sth_pendingRestore->execute() or die $sth_pendingRestore->errstr;
while (my ($domain_id,$name,$exdate) = $sth_pendingRestore->fetchrow_array) {
	$dbh->do("UPDATE `domain` SET `rgpstatus` = 'redemptionPeriod' WHERE `id` = '$domain_id'") or die $dbh->errstr;
	print strftime("%Y-%m-%d %H:%M:%S", localtime);
	print " - $domain_id\t|\t$name\t|\tback to redemptionPeriod from pendingRestore exdate:$exdate";
	print "\n";
}
$sth_pendingRestore->finish;









my $sth_delete = $dbh->prepare("SELECT `id`,`name`,`exdate` FROM `domain` WHERE CURRENT_TIMESTAMP > DATE_ADD(`delTime`, INTERVAL 35 DAY) AND `rgpstatus` = 'pendingDelete'") or die $dbh->errstr;
$sth_delete->execute() or die $sth_delete->errstr;

while (my ($domain_id,$name,$exdate) = $sth_delete->fetchrow_array) {
	my $sth_status = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
	$sth_status->execute($domain_id) or die $sth_status->errstr;

	my $delete_domain = 0;

	while (my ($status) = $sth_status->fetchrow_array()) {
		if ($status eq 'pendingDelete') {
			$delete_domain = 1;
		}
		if ($status =~ m/.*(serverUpdateProhibited|serverDeleteProhibited)$/) {
			$delete_domain = 0;
			next;
		}
	}
	$sth_status->finish;

	if ($delete_domain) {
		# aici facem stergerea propriu zisa
		#-----------------------------------------------
		# A domain object SHOULD NOT be deleted if subordinate host objects are associated with the domain object.
		my $sth = $dbh->prepare("SELECT `id` FROM `host` WHERE `domain_id` = ?") or die $dbh->errstr;
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
			print 'Numele de domeniu nu a fost sters cred ca este vre-o legatura cu alte obiecte' . $sth->errstr
		}
		else {
			my $curdate_id = $dbh->selectrow_array("SELECT `id` FROM `statistics` WHERE `date` = CURDATE()");
			if (!$curdate_id) {
				$dbh->do("INSERT IGNORE INTO `statistics` (`date`) VALUES(CURDATE())") or die $dbh->errstr;
			}
			$dbh->do("UPDATE `statistics` SET `deleted_domains` = `deleted_domains` + 1 WHERE `date` = CURDATE()") or die $dbh->errstr;
		}
		#-----------------------------------------------
	}

print strftime("%Y-%m-%d %H:%M:%S", localtime);
print " - $domain_id\t|\t$name\t|\tdomain:Deleted exdate:$exdate";
print "\n";
}
$sth_delete->finish;