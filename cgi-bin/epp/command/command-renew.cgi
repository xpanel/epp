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
$xp->set_namespace('domain', 'urn:ietf:params:xml:ns:domain-1.0');

my $blob = {};
$blob->{clTRID} = $cltrid;
$blob->{resultCode} = 1000;
$blob->{cmd} = 'renew';

my $node = $xp->findnodes('/epp:epp/epp:command/epp:renew')->get_node(0);
my ($registrar_id) = $dbh->selectrow_array("SELECT `id` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

my $obj;
if ($obj = $xp->find('domain:renew',$node)->get_node(0)) {
	################################################################
	#
	#			<renew><domain:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-domain:renew';
	$blob->{command} = 'renew_domain';
	$blob->{obj_type} = 'domain';

	# -  A <domain:name> element that contains the fully qualified name of the domain object whose validity period is to be extended.
	my $name = $xp->findvalue('domain:name[1]', $obj);
	$blob->{obj_id} = $name;

	my $curExpDate = $xp->findvalue('domain:curExpDate[1]', $obj);
	my $period = $xp->findvalue('domain:period[1]', $obj)->value; # 1-99
	my $period_unit = $xp->findvalue('domain:period/@unit[1]', $obj); # m|y

	if (!$name) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Indica numele de domeniu';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

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
		$blob->{human_readable_message} = 'Apartine altui registrar';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# The domain name must not be subject to clientRenewProhibited, serverRenewProhibited.
	my $sth = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
	$sth->execute($domain_id) or die $sth->errstr;
	while (my ($status) = $sth->fetchrow_array()) {
		if (($status =~ m/.*(RenewProhibited)$/) || ($status =~ /^pending/)) {
			# This response code MUST be returned when a server receives a command to transform an object that cannot be completed due to server policy or business practices.
			$blob->{resultCode} = 2304; # Object status prohibits operation
			$blob->{human_readable_message} = 'Are un status care nu permite renew, mai intii schimba statutul apoi interpretarile EPP 5730 aici';
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
	}
	$sth->finish;

	my $expiration_date = $exdate;
	$expiration_date =~ s/\s.+$//; # remove time, keep only date

	if ($curExpDate ne $expiration_date) {
		# we said current_expiration_date=$expiration_date, they say current_expiration_date=$curExpDate
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Nu coincide data expirarii';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:curExpDate';
			$blob->{obj_elem_value} = $curExpDate;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
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
		if ($date_add !~ /^(12|24|36|48|60|72|84|96|108|120)$/) {
			$blob->{resultCode} = 2306; # Parameter value policy error
			$blob->{human_readable_message} = "Sa nu fie mai mic de 1 an si nu mai mare de 10";
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

		my $after_10_years = $dbh->selectrow_array("SELECT YEAR(DATE_ADD(CURDATE(),INTERVAL 10 YEAR))");
		my $after_renew = $dbh->selectrow_array("SELECT YEAR(DATE_ADD('$exdate',INTERVAL $date_add MONTH))");

		# Domains can be renewed at any time, but the expire date cannot be more than 10 years in the future.
		if ($after_renew > $after_10_years) {
			$blob->{resultCode} = 2306; # Parameter value policy error
			$blob->{human_readable_message} = 'Domains can be renewed at any time, but the expire date cannot be more than 10 years in the future';
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

		# aici facem o verificare daca are bani pe cont
		#_________________________________________________________________________________________________________________
		my ($registrar_balance,$creditLimit) = $dbh->selectrow_array("SELECT `accountBalance`,`creditLimit` FROM `registrar` WHERE `id` = '$registrar_id' LIMIT 1");
		my $price = $dbh->selectrow_array("SELECT `$date_add` FROM `domain_price` WHERE `tldid` = '$tldid' AND `command` = 'renew' LIMIT 1");

		if (($registrar_balance + $creditLimit) < $price) {
			# This response code MUST be returned when a server attempts to execute a billable operation and the command cannot be completed due to a client-billing failure.
			$blob->{resultCode} = 2104; # Billing failure
			$blob->{human_readable_message} = "Nu sunt bani pe cont pentru renew";
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}
		#_________________________________________________________________________________________________________________

		my ($from) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
		$sth = $dbh->prepare("UPDATE `domain` SET `exdate` = DATE_ADD(`exdate`, INTERVAL ? MONTH), `rgpstatus` = ?, `renewPeriod` = ?, `renewedDate` = CURRENT_TIMESTAMP WHERE `id` = ?") or die $dbh->errstr;
		$sth->execute($date_add,'renewPeriod',$date_add,$domain_id) or die $sth->errstr;
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
			# ii luam banii de pe cont
			# ii mai verificam contul daca nu are destui ii punem in poll un mesaj
			# de vazut cu poll sa nu ii punem de mai multe ori acelas mesaj

			#_________________________________________________________________________________________________________________
			$dbh->do("UPDATE `registrar` SET `accountBalance` = (`accountBalance` - $price) WHERE `id` = '$registrar_id'") or die $dbh->errstr;
			$dbh->do("INSERT INTO `payment_history` (`registrar_id`,`date`,`description`,`amount`) VALUES('$registrar_id',CURRENT_TIMESTAMP,'renew domain $name for period $date_add MONTH','-$price')") or die $dbh->errstr;
			#_________________________________________________________________________________________________________________

			my ($to) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `id` = '$domain_id' LIMIT 1");
			$sth = $dbh->prepare("INSERT INTO `statement` (`registrar_id`,`date`,`command`,`domain_name`,`length_in_months`,`from`,`to`,`amount`) VALUES(?,CURRENT_TIMESTAMP,?,?,?,?,?,?)") or die $dbh->errstr;
			$sth->execute($registrar_id,$blob->{cmd},$name,$date_add,$from,$to,$price) or die $sth->errstr;
			#_________________________________________________________________________________________________________________
		}
	}


	my ($exdateUpdated) = $dbh->selectrow_array("SELECT `exdate` FROM `domain` WHERE `name` = '$name' LIMIT 1");

	my $curdate_id = $dbh->selectrow_array("SELECT `id` FROM `statistics` WHERE `date` = CURDATE()");
	if (!$curdate_id) {
		$dbh->do("INSERT IGNORE INTO `statistics` (`date`) VALUES(CURDATE())") or die $dbh->errstr;
	}
	$dbh->do("UPDATE `statistics` SET `renewed_domains` = `renewed_domains` + 1 WHERE `date` = CURDATE()") or die $dbh->errstr;

	$blob->{name} = $name;
	$exdateUpdated =~ s/\s/T/g;
	$exdateUpdated .= '.0Z';
	$blob->{exDate} = $exdateUpdated;
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