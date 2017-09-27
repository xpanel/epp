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
use Digest::SHA qw(sha1_base64);
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

my $blob = {};
$blob->{clTRID} = $cltrid;
$blob->{resultCode} = 1000;
$blob->{command} = 'login';

my $node = $xp->findnodes('/epp:epp/epp:command/epp:login')->get_node(0);
my ($registrar_id) = $dbh->selectrow_array("SELECT `id` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

my $date_for_svtrid = date_for_svtrid();
$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-epp:login';


my $clID = $xp->findvalue('epp:clID[1]', $node);
my $pw = $xp->findvalue('epp:pw[1]', $node);
my $lang = $xp->findvalue('epp:options/epp:lang[1]', $node);

my $digest = sha1_base64($pw);
my $sha1 = '{SHA}'.$digest.'=';

my ($clID_id) = $dbh->selectrow_array("SELECT `id` FROM `registrar` WHERE `clid` = '$clID' AND `pw` = '$sha1' LIMIT 1");

if (!$clID_id) {
	$blob->{resultCode} = 2200; # Authentication error
	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
	exit;
}

if ($clID_id == $registrar_id) {
	my $newPW_nodes = $xp->find('epp:newPW', $node);
	if ($newPW_nodes->size) {
		my $newPW = $newPW_nodes->get_node(0)->string_value;
		if ((length($newPW) < 6) || (length($newPW) > 16)) {
			$blob->{resultCode} = 2004; # Parameter value range error
				$blob->{human_readable_message} = "newPW minLength value='6', maxLength value='16'";
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:epp-1.0';
				$blob->{obj_elem} = 'newPW';
				$blob->{obj_elem_value} = $newPW;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($newPW !~ /[A-Z]/) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Password should have both upper and lower case characters';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:epp-1.0';
				$blob->{obj_elem} = 'newPW';
				$blob->{obj_elem_value} = $newPW;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($newPW !~ /[a-z]/) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Password should have both upper and lower case characters';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:epp-1.0';
				$blob->{obj_elem} = 'newPW';
				$blob->{obj_elem_value} = $newPW;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		if ($newPW !~ /\d/) {
			$blob->{resultCode} = 2005; # Parameter value syntax error
			$blob->{human_readable_message} = 'Password should contain one or more numbers';
				$blob->{optionalValue} = 1;
				$blob->{xmlns_obj} = 'xmlns';
				$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:epp-1.0';
				$blob->{obj_elem} = 'newPW';
				$blob->{obj_elem_value} = $newPW;
			my $msg = epp_writer($blob);
			print $msg;
			my $uptr = update_transaction($msg);
			exit;
		}

		# modificam parola
		my $newdigest = sha1_base64($newPW);
		my $newsha1 = '{SHA}'.$newdigest.'=';
		$dbh->do("UPDATE `registrar` SET `pw` = '$newsha1' WHERE `id` = '$clID_id'") or die $dbh->errstr;

		my $sth_htpasswd = $dbh->prepare("SELECT `clid`,`pw` FROM `registrar` ORDER BY `clid` ASC") or die $dbh->errstr;
		$sth_htpasswd->execute() or die $sth_htpasswd->errstr;
		open(HTPASSWD, '>', "/var/www/cgi-bin/epp/htpasswd/.htpasswd") or print "Failed to open file '/var/www/cgi-bin/epp/htpasswd/.htpasswd'. $! \n";
			while (my ($clid,$pw) = $sth_htpasswd->fetchrow_array()) {
				print HTPASSWD "$clid:$pw\n";
			}
		close HTPASSWD;
		$sth_htpasswd->finish;
	}
	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
else {
	$blob->{resultCode} = 2200; # Authentication error
	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}

sub update_transaction {
	my $svframe = shift;
	my $sth = $dbh->prepare("UPDATE `registryTransaction`.`transaction_identifier` SET `cmd` = ?, `obj_type` = ?, `obj_id` = ?, `code` = ?, `msg` = ?, `svTRID` = ?, `svTRIDframe` = ?, `svdate` = ?, `svmicrosecond` = ? WHERE `id` = ?") or die $dbh->errstr;
	my $date_for_sv_transaction = microsecond();
	my ($svdate,$svmicrosecond) = split(/\./, $date_for_sv_transaction);
	$sth->execute($blob->{command},$blob->{obj_type},$blob->{obj_id},$blob->{resultCode},$blob->{human_readable_message},$blob->{svTRID},$svframe,$svdate,$svmicrosecond,$transaction_id) or die $sth->errstr;
	return 1;
}